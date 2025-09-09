# Science Agent - Biological Research Automation

A CrewAI-powered system for automated biological research that processes CSV data, normalizes entities, fetches literature, predicts ADMET properties, and generates comprehensive reports.

:warning: **Disclaimer:** The following demo is intended to illustrate the usefulness and power of building multi-agent workflows for scientific research. The results shown are for demonstration purposes only and should not be considered scientifically validated or reliable.

## Overview

This project uses AI agents to automate biological research workflows:
- **Data curation**: Load and validate CSV input data
- **Entity normalization**: Standardize biological entities (compounds, proteins, peptides)
- **Literature research**: Fetch relevant PubMed references
- **Web scraping**: Extract content from PubMed URLs
- **ADMET prediction**: Predict absorption, distribution, metabolism, excretion, and toxicity properties
- **Report generation**: Compile all findings into a Markdown report

## Prerequisites

- Docker and Docker Compose
- OpenAI API key (for GPT-4o model access)
- Sample CSV file with biological entities

## Quick Start

1. **Set up environment variables**:
   Create a `.env` file in the `science_agent` directory with:
   ```
   OPENAI_API_KEY=your_openai_api_key_here
   MODEL=gpt-4o
   ADMETICA_API=http://admetica-api:8080
   INPUT_CSV=./sample_data.csv
   REPORT_FILE=/app/output/report.md
   ```

2. **Prepare your input data**:
   Place a CSV file in the `science_agent` directory with columns for:
   - `entity_type` (compound, protein, or peptide)
   - `identifier` (SMILES for compounds, UniProt ID for proteins)
   - `name` (optional)
   - `context_tags` (comma-separated tags for literature search)

3. **Run the system**:
   ```bash
   docker-compose up
   ```

4. **Check outputs**:
   Results will be saved in the `output` directory, including:
   - `report.md`: Comprehensive research report
   - JSON files with normalized entities, literature references, and ADMET predictions

## Project Structure

```
science_agent/
├── src/science_agent/
│   ├── config/
│   │   ├── agents.yaml    # Agent definitions
│   │   └── tasks.yaml     # Task workflow
│   ├── tools/
│   │   └── custom_tool.py # Custom tools implementation
│   ├── crew.py           # Crew configuration
│   └── main.py           # Entry point
├── sample_data.csv       # Example input data
└── .env                  # Environment variables
```

## Components

### Agents
- **Curator**: Validates and normalizes biological entities to standard IDs
- **Researcher**: Retrieves high-signal literature from PubMed
- **Web Scraper**: Extracts specific information from websites
- **Analyst**: Produces ADMET/toxicity estimates using admetica-api
- **Reporter**: Assembles concise, auditable Markdown reports

### Tasks
1. **task_load**: Load CSV file and return JSON rows
2. **task_normalize**: Normalize entities to standard IDs
3. **task_lit**: Fetch PubMed references for each entity
4. **task_web_scrapper**: Scrape abstract content from PubMed URLs
5. **task_admet**: Predict ADMET properties for compounds
6. **task_report**: Compile final Markdown report

### Tools
- **LoadCSVTool**: Loads and validates CSV files
- **NormalizeEntitiesTool**: Standardizes biological identifiers
- **FetchPubMedTool**: Searches and retrieves PubMed references
- **PredictADMETTool**: Interfaces with admetica-api for predictions
- **CompileReportTool**: Generates comprehensive research reports

## Input Format

The system expects a CSV file with the following columns:
- `entity_type`: Type of biological entity (compound, protein, peptide)
- `identifier`: Entity identifier (SMILES for compounds, UniProt ID for proteins)
- `name`: Optional descriptive name
- `context_tags`: Optional comma-separated tags for literature search context

Example CSV:
```csv
entity_type,identifier,name,context_tags
compound,CC(=O)OC1=CC=CC=C1C(=O)O,Aspirin,analgesic,anti-inflammatory
protein,P12345,EGFR,kinase,cancer
```

## Output

The system generates:
1. **Normalized entities JSON**: Standardized identifiers and metadata
2. **Literature references JSON**: PubMed citations and URLs
3. **ADMET predictions JSON**: Toxicity and pharmacokinetic predictions
4. **Markdown report**: Comprehensive research summary with:
   - Entity details
   - Literature summaries with PubMed URLs
   - ADMET predictions
   - Contextual information

## Customization

Modify the configuration files to customize the workflow:
- `agents.yaml`: Adjust agent roles and models
- `tasks.yaml**: Modify task sequences and dependencies
- `custom_tool.py`: Extend or modify tool functionality

## Troubleshooting

- Ensure Docker is running and has sufficient resources
- Verify OpenAI API key is valid and has sufficient credits
- Check that the input CSV file exists and is properly formatted
- Monitor Docker logs for any service errors

## License

This project is provided as-is for research and educational purposes.