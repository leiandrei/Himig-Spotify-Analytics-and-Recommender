import logging

def log(name: str) -> logging.Logger:

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
        force=True
    )

    return logging.getLogger(name)