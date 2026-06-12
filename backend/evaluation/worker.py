import argparse

from evaluation.tasks import run_ragas_evaluation_job


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a RAGAS evaluation job.")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args()

    run_ragas_evaluation_job(job_id=args.job_id, user_id=args.user_id)


if __name__ == "__main__":
    main()
