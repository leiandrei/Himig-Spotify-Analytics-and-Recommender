from logger import log
from dotenv import load_dotenv

import psycopg
import os

load_dotenv()

HOST = os.getenv('DB_HOST')
USERNAME = os.getenv('DB_USER')
PASSWORD = os.getenv('DB_PASS')
DB_NAME = os.getenv('DB_NAME')
PORT = os.getenv('DB_PORT')

logger = log(__name__)

DB_QUERIES = [
    """
    CREATE TABLE IF NOT EXISTS dim_artists(
        artists_id INT PRIMARY KEY,
        primary_artist_name VARCHAR(256) NOT NULL,
        artist_listeners BIGINT,
        artist_playcount BIGINT,
        tags TEXT,
        similar_artists TEXT,
        num_tags INT,
        num_similar_artists INT    
    );
    """,

    """
    CREATE TABLE IF NOT EXISTS dim_tracks(
        track_id VARCHAR(128) PRIMARY KEY,
        release_date DATE,
        song_name VARCHAR(256) NOT NULL,
        album_name VARCHAR(256),
        duration_min NUMERIC(6, 2),
        artists_id INT,
        FOREIGN KEY (artists_id) REFERENCES dim_artists(artists_id) ON DELETE SET NULL
    );
    """,

    """
    CREATE TABLE IF NOT EXISTS fact_interactions(
        interaction_id INT PRIMARY KEY,
        track_id VARCHAR(128) NOT NULL,
        interaction_type VARCHAR(128) NOT NULL,
        FOREIGN KEY (track_id) REFERENCES dim_tracks(track_id) ON DELETE CASCADE 
    );
    """
]

CSV_MAP = [{
        'table' : 'dim_artists',
        'path' : '../data/processed/to_db/dim_artists.csv'
    }, 

    {
        'table' : 'dim_tracks',
        'path' : '../data/processed/to_db/dim_tracks.csv'
    }, 

    {
        'table' : 'fact_interactions',
        'path' : '../data/processed/to_db/fact_interactions.csv'
    }]


def db_client() -> psycopg.Connection:

    logger.info(f"Connecting to the DB Server using DB Credentials..")
    
    try:
        db_creds =  psycopg.connect(
            host=HOST,
            user=USERNAME,
            port=PORT,
            dbname=DB_NAME,
            password=PASSWORD
        )

        logger.info(f"Connection to the Spotify DB Server Established.")
        return db_creds

    except Exception as e:
        logger.error(f"Unexpected Error Occurred. Unable to Establish Connection to the DB: {e}")
        raise


def load_db():

    conn = db_client()

    try:
        with conn.cursor() as curr:

            for queries in DB_QUERIES:
                curr.execute(queries)

            for maps in CSV_MAP:
                table = maps['table']
                path = maps['path']

                if not os.path.exists(path):
                    logger.warning(f"File Not Found in the following Path: {path}, skipping table: {table}")
                    continue

                logger.info(f"Ingesting {path} into {table}...")
                curr.execute(f"TRUNCATE TABLE {table} CASCADE;")

                with open(path, 'r', encoding='utf-8') as csv_file:
                    with curr.copy(f"COPY {table} FROM STDIN WITH (FORMAT CSV, HEADER TRUE)") as copy:
                        while chunk := csv_file.read(65536):
                            copy.write(chunk)

                logger.info(f"The table {table} has been successfully loaded.")

            conn.commit()
            logger.info("All tables have been successfully stored to PostgreSQL")

    except Exception as e:
        conn.rollback()
        logger.error(f"Unexpected Error Occured while loading to the Database: {e}")
        raise

    finally:
        conn.close()
        logger.info("Database Connection has been closed.")

if __name__ == "__main__":
    
    logger.info("Orchestrating Database Loading to PostgreSQL")
    load_db()