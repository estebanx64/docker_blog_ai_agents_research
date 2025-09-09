#!/usr/bin/env python
import os
import warnings

from dotenv import load_dotenv

from science_agent.crew import ScienceAgent

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

# This main file is intended to be a way for you to run your
# crew locally, so refrain from adding unnecessary logic into this file.
# Replace with inputs you want to test with, it will automatically
# interpolate any tasks and agents information

load_dotenv(override=True)


def run():
    """
    Run the crew.
    """
    input_file = os.getenv("INPUT_CSV")
    inputs = {"input_csv": input_file}

    try:
        result = ScienceAgent().crew().kickoff(inputs=inputs)
        print(result.raw)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


if __name__ == "__main__":
    run()
