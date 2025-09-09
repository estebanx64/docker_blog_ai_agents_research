from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai_tools import ScrapeElementFromWebsiteTool

from .tools.custom_tool import (
    CompileReportTool,
    FetchPubMedTool,
    LitWebSummaries,
    LoadCSVTool,
    NormalizeEntitiesTool,
    PredictADMETTool,
)

scrape_tool = ScrapeElementFromWebsiteTool()


@CrewBase
class ScienceAgent:
    agents_config = "config/agents.yaml"
    tasks_config = "config/tasks.yaml"

    @agent
    def curator(self) -> Agent:
        return Agent(
            config=self.agents_config["curator"],  # type: ignore[index]
            allow_delegation=False,
        )

    @agent
    def researcher(self) -> Agent:
        return Agent(
            config=self.agents_config["researcher"],  # type: ignore[index]
            allow_delegation=False,
        )

    @agent
    def web_scraper(self) -> Agent:
        return Agent(
            config=self.agents_config["web_scraper"],  # type: ignore[index]
            allow_delegation=False,
            tools=[scrape_tool],
        )

    @agent
    def analyst(self) -> Agent:
        return Agent(
            config=self.agents_config["analyst"],  # type: ignore[index]
            allow_delegation=False,
        )

    @agent
    def reporter(self) -> Agent:
        return Agent(
            config=self.agents_config["reporter"],  # type: ignore[index]
            allow_delegation=False,
        )

    @task
    def task_load(self) -> Task:
        return Task(
            config=self.tasks_config["task_load"],  # type: ignore[index]
            tools=[LoadCSVTool()],
        )

    @task
    def task_normalize(self) -> Task:
        return Task(
            config=self.tasks_config["task_normalize"],  # type: ignore[index]
            tools=[NormalizeEntitiesTool()],
        )

    @task
    def task_lit(self) -> Task:
        return Task(
            config=self.tasks_config["task_lit"],  # type: ignore[index]
            tools=[FetchPubMedTool()],
        )

    @task
    def task_web_scrapper(self) -> Task:
        return Task(
            config=self.tasks_config["task_web_scrapper"],  # type: ignore[index]
            output_json=LitWebSummaries,
        )

    @task
    def task_admet(self) -> Task:
        return Task(
            config=self.tasks_config["task_admet"],  # type: ignore[index]
            tools=[PredictADMETTool()],
        )

    @task
    def task_report(self) -> Task:
        return Task(
            config=self.tasks_config["task_report"],  # type: ignore[index]
            tools=[CompileReportTool()],
        )

    @crew
    def crew(self) -> Crew:
        return Crew(
            agents=self.agents,  # type: ignore[index] Automatically created by the @agent decorator
            tasks=self.tasks,  # type: ignore Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
        )
