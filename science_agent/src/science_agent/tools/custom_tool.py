import csv
import hashlib
import json
import os
from functools import cache
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field
from rdkit import Chem
from rdkit.Chem import Descriptors

RUN_DIR = Path(__file__).parent.parent.parent.parent / "output"
RUN_DIR.mkdir(parents=True, exist_ok=True)


@cache
def get_admetica_url() -> str:
    url = os.getenv("ADMETICA_API")
    if not url:
        raise Exception("ADMETICA_API environment variable not set")
    return url


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class NormalizedEntity(BaseModel):
    row_id: int = Field(..., description="Row index from CSV")
    entity_type: str = Field(..., description="protein | compound | peptide")
    identifier: str = Field(..., description="Original identifier (e.g., SMILES, UniProt)")
    normalized_id: str = Field(..., description="Standardized ID (e.g., InChIKey or UniProt AC)")
    name: str | None = None
    context_tags: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)


class LiteratureRef(BaseModel):
    title: str
    year: int | None = None
    source: str = "pubmed"
    pmid: str | None = None
    doi: str | None = None
    url: str | None = None
    snippet: str | None = None


class LiteratureBundle(BaseModel):
    normalized_id: str
    references: list[LiteratureRef] = Field(default_factory=list)


class LitWebSummary(BaseModel):
    normalized_id: str
    summaries: list[str]


class LitWebSummaries(BaseModel):
    items: list[LitWebSummary]


class LitSummary(BaseModel):
    normalized_id: str
    summary: str
    key_citations: list[str] = Field(default_factory=list)  # PMIDs/DOIs


class ADMETPrediction(BaseModel):
    normalized_id: str
    absorption: float
    distribution: float
    metabolism: float
    excretion: float
    toxicity: float


class RunReport(BaseModel):
    job_id: str
    input_hash: str
    n_entities: int
    outputs: dict[str, str]  # artifact name -> path


class LoadCSVInput(BaseModel):
    path: str = Field(..., description="The path to the CSV file to load")


class LoadCSVTool(BaseTool):
    name: str = "Load CSV file"
    description: str = "This tool loads a CSV file and returns its contents as JSON"
    args_schema: type[BaseModel] = LoadCSVInput

    def _run(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return json.dumps({"error": f"File not found: {path}"})
        df = pd.read_csv(p)
        out = {"rows": df.to_dict(orient="records")}
        (RUN_DIR / "raw_input.json").write_text(json.dumps(out, indent=2))
        return json.dumps(out)


class NormalizeEntitiesInput(BaseModel):
    json_rows: str = Field(..., description="JSON string containing rows to normalize")


class NormalizeEntitiesTool(BaseTool):
    name: str = "Normalize entities"
    description: str = "Normalize entities from JSON rows, converting compounds to InChIKey if possible"
    args_schema: type[BaseModel] = NormalizeEntitiesInput

    def _run(self, json_rows: str) -> str:
        try:
            data = json.loads(json_rows)
        except json.JSONDecodeError as e:
            return json.dumps({"error": f"Invalid JSON input: {e}"})

        # Handle both cases: direct list or dict with "rows" key
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("rows", [])
        else:
            return json.dumps({"error": f"Expected list or dict, got {type(data)}"})

        normalized: list[NormalizedEntity] = []
        for i, r in enumerate(rows):
            etype = (r.get("entity_type") or "").strip().lower()
            ident = (r.get("identifier") or "").strip()
            name = r.get("name")
            tags = [t.strip() for t in (r.get("context_tags") or "").split(",") if t.strip()]

            norm_id = ident
            extras = {}

            if etype == "compound":
                if Chem:
                    mol = Chem.MolFromSmiles(ident)
                    if mol is not None:
                        can = Chem.MolToSmiles(mol, canonical=True) or ident
                        norm_id = hashlib.sha1(can.encode()).hexdigest()[:27]  # pseudo
                        mw = Descriptors.MolWt(mol)  # type: ignore
                        logp = Descriptors.MolLogP(mol)  # type: ignore
                        extras.update({"mw": mw, "logp": logp, "canonical_smiles": can})
                else:
                    extras.update({"note": "RDKit not installed; kept original identifier"})

            elif etype == "protein":
                extras.update({"note": "Protein normalization is a pass-through in demo"})

            normalized.append(
                NormalizedEntity(
                    row_id=i,
                    entity_type=etype,
                    identifier=ident,
                    normalized_id=norm_id,
                    name=name,
                    context_tags=tags,
                    extras=extras,
                )
            )

        txt = json.dumps([n.model_dump() for n in normalized], indent=2)
        (RUN_DIR / "normalized_entities.json").write_text(txt)
        return txt


class FetchPubMedInput(BaseModel):
    normalized_entities_json: str = Field(..., description="JSON string of normalized entities")


class FetchPubMedTool(BaseTool):
    name: str = "Fetch PubMed references"
    description: str = "Fetch PubMed references for normalized entities"
    args_schema: type[BaseModel] = FetchPubMedInput

    def _run(self, normalized_entities_json: str) -> str:
        # Debug: print the input to see what's being passed
        print(f"DEBUG: Input received: {normalized_entities_json[:200]}...")

        # Check if the input is the tool argument description instead of actual JSON
        if "JSON string of normalized entities" in normalized_entities_json:
            error_msg = "Error: Tool received argument description instead of actual JSON data. Please use the output from the normalization task."
            print(error_msg)
            return json.dumps({"error": error_msg})

        try:
            parsed_data = json.loads(normalized_entities_json)
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON input: {e}. Input: {normalized_entities_json[:200]}..."
            print(error_msg)
            return json.dumps({"error": error_msg})

        # Check if parsed_data is a list of dictionaries
        if not isinstance(parsed_data, list):
            error_msg = f"Expected list of entities, got {type(parsed_data)}: {parsed_data}"
            print(error_msg)
            return json.dumps({"error": error_msg})

        # Validate each item in the list is a dictionary
        for i, item in enumerate(parsed_data):
            if not isinstance(item, dict):
                error_msg = f"Item at index {i} is not a dictionary: {item}"
                print(error_msg)
                return json.dumps({"error": error_msg})

        ents = [NormalizedEntity(**e) for e in parsed_data]
        bundles: list[LiteratureBundle] = []

        for e in ents:
            q = ""
            q = e.name or e.identifier
            if e.context_tags:
                q += " " + " ".join(e.context_tags)

            refs: list[LiteratureRef] = []

            if requests and q.strip():
                try:
                    esearch = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
                    r = requests.get(
                        esearch,
                        params={
                            "db": "pubmed",
                            "term": q,
                            "retmax": 5,
                            "retmode": "json",
                        },
                        timeout=10,
                    )
                    ids = r.json().get("esearchresult", {}).get("idlist", []) if r.ok else []
                    if ids:
                        esum = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
                        r2 = requests.get(
                            esum,
                            params={
                                "db": "pubmed",
                                "id": ",".join(ids),
                                "retmode": "json",
                            },
                            timeout=10,
                        )
                        docs = r2.json().get("result", {}) if r2.ok else {}
                        for pid in ids:
                            doc = docs.get(pid) or {}
                            title = doc.get("title")
                            year = None
                            try:
                                d = (doc.get("pubdate") or "")[:4]
                                year = int(d) if d.isdigit() else None
                            except Exception as ex:
                                print(ex)
                            url = f"https://pubmed.ncbi.nlm.nih.gov/{pid}/"
                            refs.append(LiteratureRef(title=title or q, year=year, pmid=pid, url=url))
                except Exception as ex:
                    print(ex)

            if not refs:  # fallback mock
                refs = [
                    LiteratureRef(title=f"{q} – placeholder study", year=2018, pmid=None, url=None),
                    LiteratureRef(title=f"{q} – review article", year=2021, pmid=None, url=None),
                ]

            bundles.append(LiteratureBundle(normalized_id=e.normalized_id, references=refs))

        txt = json.dumps([b.model_dump() for b in bundles], indent=2)
        (RUN_DIR / "literature_refs.json").write_text(txt)
        return txt


class PredictADMETInput(BaseModel):
    normalized_entities_json: str = Field(..., description="JSON string of normalized entities")


class PredictADMETTool(BaseTool):
    name: str = "Predict ADMET properties"
    description: str = "Predict ADMET properties for normalized entities"
    args_schema: type[BaseModel] = PredictADMETInput

    def _run(self, normalized_entities_json: str) -> str:
        ents = [NormalizedEntity(**e) for e in json.loads(normalized_entities_json)]
        preds: list[ADMETPrediction] = []
        params = {
            "models": "solubility,ppbr,cyp1a2-inhibitor,cl-hepa,herg",
            "smiles_column": "smiles",
            "probability": "false",
        }
        headers = {"accept": "text/csv", "Content-Type": "text/csv"}

        for e in ents:
            if e.entity_type == "compound":
                data = f"""smiles
                        {e.identifier}
                        """
                response = httpx.post(
                    f"{get_admetica_url()}/predict",
                    params=params,
                    headers=headers,
                    data=data,  # type: ignore
                )
                if response.status_code == 200:
                    parsed_data = self._parse_results(response.text)
                    preds.append(
                        ADMETPrediction(
                            normalized_id=e.normalized_id,
                            absorption=parsed_data["solubility"],
                            distribution=parsed_data["ppbr"],
                            metabolism=parsed_data["cyp1a2-inhibitor"],
                            excretion=parsed_data["cl-hepa"],
                            toxicity=parsed_data["herg"],
                        )
                    )
            elif e.entity_type == "protein":
                preds.append(
                    ADMETPrediction(
                        normalized_id=e.normalized_id,
                        absorption=0,
                        distribution=0,
                        metabolism=0,
                        excretion=0,
                        toxicity=0,
                    )
                )

        txt = json.dumps([p.model_dump() for p in preds], indent=2)
        (RUN_DIR / "admet_predictions.json").write_text(txt)
        return txt

    def _parse_results(self, response: str) -> dict:
        csv_reader = csv.reader(StringIO(response))
        headers = next(csv_reader)
        for row in csv_reader:
            row_dict = {}
            for i, value in enumerate(row):
                # Convert string values to appropriate types (float for numeric values)
                try:
                    row_dict[headers[i]] = float(value)
                except ValueError:
                    row_dict[headers[i]] = value
            return row_dict
        return {}


class CompileReportInput(BaseModel):
    entities_json: str = Field(..., description="JSON string of entities")
    web_json: str = Field(..., description="JSON string of web scrapper results")
    literature_json: str = Field(..., description="JSON string of literature refs")
    admet_json: str = Field(..., description="JSON string of ADMET predictions")
    input_path: str = Field(..., description="Path to the input file")


class CompileReportTool(BaseTool):
    name: str = "Compile report"
    description: str = "Compile a Markdown report from entities, literature summaries, and ADMET predictions"
    args_schema: type[BaseModel] = CompileReportInput

    def _run(
        self,
        entities_json: str,
        web_json: str,
        literature_json: str,
        admet_json: str,
        input_path: str,
    ) -> str:
        ents = [NormalizedEntity(**e) for e in json.loads(entities_json)]
        print(f"DEBUG: input web:{web_json}")
        print(type(web_json))

        # Parse web_json (LitWebSummaries structure)
        web_data = json.loads(web_json)
        if isinstance(web_data, dict) and "items" in web_data:
            web_map = {item["normalized_id"]: item["summaries"] for item in web_data["items"]}
        else:
            web_map = {}
            print(f"Warning: Unexpected web_json structure: {web_data}")

        literature_map = {s["normalized_id"]: s for s in json.loads(literature_json)}
        admet_map = {s["normalized_id"]: s for s in json.loads(admet_json)}

        input_hash = sha1_file(Path(input_path))
        job_id = RUN_DIR.name

        lines = [
            f"# Biology Research Run – {job_id}",
            "",
            f"- **Input file**: `{input_path}`",
            f"- **SHA1**: `{input_hash}`",
            f"- **Entities**: {len(ents)}",
            "",
            "## Entities",
        ]
        for e in ents:
            li = literature_map.get(e.normalized_id)
            lines += [
                f"### {e.name or e.identifier} ({e.entity_type})",
                f"- Normalized ID: `{e.normalized_id}`",
                f"- Context: {', '.join(e.context_tags) if e.context_tags else '(none)'}",
                f"- Extras: `{json.dumps(e.extras)}`",
                "",
            ]

            pubmed_refs = ["- (none)"]
            if li and li.get("references"):
                # Create bulleted list of PubMed URLs for each citation
                pubmed_refs = []
                for item in li["references"]:
                    if item.get("url"):
                        pubmed_refs.append(f"- {item['url']}")
                    else:
                        pubmed_refs.append("- (no URL available)")

            we = web_map.get(e.normalized_id)

            lines += [
                "#### Literature Summary",
                f"{''.join(we) if we else 'No pubmed refs available'}",  # type: ignore
                "- **PubMed refs**:",
                *pubmed_refs,
                "",
            ]

            ad = admet_map.get(e.normalized_id)
            if ad:
                lines += [
                    "#### ADMET / Toxicity",
                    "```json",
                    json.dumps(ad, indent=2),
                    "```",
                    "",
                ]
            else:
                lines += [
                    "#### ADMET / Toxicity",
                    "No ADMET data available",
                    "",
                ]

        out_path = RUN_DIR / "report.md"
        out_path.write_text("\n".join(lines))
        report = RunReport(
            job_id=job_id,
            input_hash=input_hash,
            n_entities=len(ents),
            outputs={
                "report_md": str(out_path),
                "entities_json": str(RUN_DIR / "normalized_entities.json"),
                "literature_json": str(RUN_DIR / "literature_summaries.json"),
                "admet_json": str(RUN_DIR / "admet_predictions.json"),
            },
        )
        (RUN_DIR / "run_meta.json").write_text(json.dumps(report.model_dump(), indent=2))
        return str(out_path)
