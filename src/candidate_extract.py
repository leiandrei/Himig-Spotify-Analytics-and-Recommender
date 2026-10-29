from typing import Dict, List, Any, Set
from spotipy.oauth2 import SpotifyOAuth
from dotenv import load_dotenv
from logger import log

import spotipy
import pandas as pd
import pylast
import time 
import json
import os

logger = log(__name__)

load_dotenv()

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = os.getenv('REDIRECT_URI')

API_KEY = os.getenv('API_KEY')
SHARED_SEC = os.getenv('SHARED_SECRET')

auth_mngr = SpotifyOAuth(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    redirect_uri=REDIRECT_URI,
    scope='user-read-private'
)

network = pylast.LastFMNetwork(api_key=API_KEY, api_secret=SHARED_SEC)
network.enable_rate_limit()

sp = spotipy.Spotify(auth_manager=auth_mngr)

def get_possible_candidates(filepath: str) -> Set[str]:

    try:

        lfm = pd.read_csv(filepath)

        lfm['similar_artists_list'] = lfm['similar_artists'].fillna('').apply(
            lambda x: [artist.strip() for artist in str(x).split(',') if artist.strip()]
        )

        all_similar_artists = lfm['similar_artists_list'].explode().dropna()

        unique_candidates = set(all_similar_artists)
        known_artists = set(lfm['artist'].dropna())

        unheard_candidates = unique_candidates - known_artists

        logger.info(f"Total Known Artists: {len(known_artists)}")
        logger.info(f"Total New Candidate Artists: {len(unique_candidates)}")

        return unheard_candidates

    except Exception as e:
        logger.error(f"Error occured while extracting artists: {e}")
        return set()
    

def fetch_candidate_toptracks(artist_name: str) -> List[Dict[str, Any]]:

    candidate_tracks = []

    try:

        query_ = f'artist:"{artist_name}"'
        search_ = sp.search(q=query_, type='track', limit=10, market='PH')

        if not search_ or 'tracks' not in search_:
            logger.warning(f"Spotify search returned invalid data for: {artist_name}")
            return []

        items = search_['tracks']['items']

        if not items:
            logger.warning(f"Spotify search returned no tracks for: {artist_name}")
            return []

        for track in items:

            candidate_tracks.append({
                'id' : track['id'],
                'name' : track['name'],
                'duration_ms' : track['duration_ms'],
                'explicit' : track['explicit'],
                'album_name' : track['album']['name'],
                'release_date' : track['album']['release_date'],
                'album_image_url' : track['album']['images'][0]['url'] if track['album']['images'] else None,
                'primary_artist_name' : track['artists'][0]['name'],
                'primary_artist_id' : track['artists'][0]['id'],
                'all_artists': ", ".join([a['name'] for a in track['artists']])
            })


        return candidate_tracks

    except spotipy.SpotifyException as e:
        logger.error(f"Spotify API Error Occured: {e}")
        return []

    except Exception as e:
        logger.error(f"Unexpected Error Occured: {e}")
        return []

def main(lastfm_path: str, output_path: str, output_csv: str) -> None:

    try:

        candidates = get_possible_candidates(lastfm_path)
        all_extracted_tracks = []
        processed_artists = set()

        if os.path.exists(output_path):
            with open(output_path, 'r', encoding='utf-8') as file:
                try:

                    all_extracted_tracks = json.load(file)
                    processed_artists = {track['primary_artist_name'] for track in all_extracted_tracks}
                    logger.info(f"Loaded {len(all_extracted_tracks)} from {output_path}")

                except json.JSONDecodeError:
                    logger.warning(f"Unexpected Error Occured when opening JSON file")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        logger.info(f"Extracting Candidate Tracks from Artists...")

        for idx, artists in enumerate(candidates):

            if artists in processed_artists:
                continue

            logger.info(f"[{idx+1}/{len(candidates)}] Fetching top tracks for: {artists}")

            tracks = fetch_candidate_toptracks(artists)
            all_extracted_tracks.extend(tracks)

            if (idx + 1) % 20 == 0:
                with open(output_path, 'w', encoding='utf-8') as file:
                    json.dump(all_extracted_tracks, file, indent=4)
                    logger.info("Checkpoint: Candidate tracks safely saved to disk")

            time.sleep(0.2)

        with open(output_path, 'w', encoding='utf-8') as file:
            json.dump(all_extracted_tracks, file, indent=4)

        os.makedirs(os.path.dirname(output_csv), exist_ok=True)

        df = pd.DataFrame(all_extracted_tracks)

        if not df.empty:
            df = df.drop_duplicates(subset=['id'])
            df.to_csv(output_csv, index=False)
            logger.info(f"Candidate Tracks Extraction is Complete! File Saved to: {output_csv}")
        else:
            logger.warning("No tracks were extracted. Try again.")

    except Exception as e:
        logger.info(f"Unexpected Error has Occured: {e}")
        raise

def artists_pool(output_csv: str) -> None:

    filepaths = [
        '../data/processed/clean_data/long_top_tracks.csv',
        '../data/processed/clean_data/saved_tracks.csv',
        '../data/processed/clean_data/recently_played.csv'
    ]

    unique_artists = set()

    for path in filepaths:
        try:
            if os.path.exists(path):
                df = pd.read_csv(path)

                if 'primary_artist_name' in df.columns:
                    artists = df['primary_artist_name'].dropna().astype(str).str.strip().unique()
                    unique_artists.update(artists)
                    logger.info(f"Loaded {len(artists)} unique artists from {os.path.basename(path)}")

                else:
                    logger.warning('Column "primary_artist_name" is missing from the path')

            else:
                logger.warning(f"File not found: {path}")

        except Exception as e:
            logger.error(f"Unexpected Error Occured: {e}")

    pooling = pd.DataFrame({'primary_artist_name' : sorted(list(unique_artists))})

    if os.path.dirname(output_csv):
        os.makedirs(os.path.dirname(output_csv), exist_ok=True)

    pooling.to_csv(output_csv, index=False)
    
    logger.info(f"Total deduplicated artist pool: {len(pooling)} artists.")
    logger.info(f"Saved to: {output_csv}")

def extract_temporal_feats(network: pylast.LastFMNetwork, artists_name: str) -> Dict[str, Any]:

    try:
        artist = network.get_artist(artists_name)

        return {
            'artist_listeners' : int(artist.get_listener_count()),
            'artist_playcount' : int(artist.get_playcount())
        }

    except pylast.WSError as e:
        logger.warning(f"Unexpected Error Occurred when connecting to Last.Fm API: {e}") 

    except Exception as e:
        logger.error(f"Unexpected Error Occurred: {e}")

    return {'artist_listeners' : 0, 'artist_playcount' : 0}

def extract_full_lastfm_feats(network: pylast.LastFMNetwork, artist_name: str) -> Dict[str, Any]:
    try:
        artist = network.get_artist(artist_name)

        listeners = int(artist.get_listener_count())
        playcount = int(artist.get_playcount())

        top_tags = artist.get_top_tags(limit=10)
        tags_str = ", ".join([tag.item.get_name() for tag in top_tags]) if top_tags else ""

        similar = artist.get_similar(limit=10)
        similar_str = ", ".join([sim.item.get_name() for sim in similar]) if similar else ""

        return {
            'artist_listeners': listeners,
            'artist_playcount': playcount,
            'tags': tags_str,
            'similar_artists': similar_str
        }

    except pylast.WSError as e:
        logger.warning(f"Last.Fm API Error for {artist_name}: {e}") 
    except Exception as e:
        logger.error(f"Unexpected Error for {artist_name}: {e}")

    return {
        'artist_listeners': 0, 
        'artist_playcount': 0, 
        'tags': '', 
        'similar_artists': ''
    }

def orchestrate_pooling(pool_csv: str, output_json: str, output_csv: str) -> None:
    logger.info("Building unique artist pool")
    artists_pool(pool_csv)

    if not os.path.exists(pool_csv):
        logger.error(f"Pool creation failed. Cannot find {pool_csv}")
        return
        
    df_pool = pd.read_csv(pool_csv)
    total_artists = len(df_pool)
    enriched_data = []
    processed_artists = set()

    if os.path.exists(output_json):
        with open(output_json, 'r', encoding='utf-8') as f:
            try:
                enriched_data = json.load(f)
                processed_artists = {item['primary_artist_name'] for item in enriched_data}
                logger.info(f"Loaded {len(enriched_data)} artists from checkpoint.")
            except json.JSONDecodeError:
                logger.warning("Checkpoint JSON is empty or corrupted. Starting fresh.")

    if os.path.dirname(output_json):
        os.makedirs(os.path.dirname(output_json), exist_ok=True)

    for idx, row in df_pool.iterrows():
        artist_name = row['primary_artist_name']

        if artist_name in processed_artists:
            continue

        logger.info(f"[{idx + 1}/{total_artists}] Extracting temporal stats for: {artist_name}")
        
        stats = extract_temporal_feats(network, artist_name)

        enriched_record = {'primary_artist_name': artist_name, **stats}
        enriched_data.append(enriched_record)

        if (idx + 1) % 20 == 0:
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump(enriched_data, f, indent=4)
            logger.info(" Checkpoint: Temporal stats saved to disk.")

        time.sleep(0.25)

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(enriched_data, f, indent=4)
        
    if os.path.dirname(output_csv):
        os.makedirs(os.path.dirname(output_csv), exist_ok=True)
        
    final_df = pd.DataFrame(enriched_data)
    final_df.to_csv(output_csv, index=False)
    logger.info(f"Orchestration complete! Saved {len(final_df)} artists to: {output_csv}")

def backfill_candidate_artists(candidate_tracks_csv: str, output_json: str, output_csv: str) -> None:

    logger.info("Initiating Last.fm backfill for candidate artists...")
    df_tracks = pd.read_csv(candidate_tracks_csv)
    unique_candidates = df_tracks['primary_artist_name'].dropna().astype(str).str.strip().unique()
    
    enriched_data = []
    processed_artists = set()

    if os.path.exists(output_json):
        with open(output_json, 'r', encoding='utf-8') as f:
            try:
                enriched_data = json.load(f)
                processed_artists = {item['primary_artist_name'] for item in enriched_data}
                logger.info(f"Loaded {len(enriched_data)} candidate artists from checkpoint.")
            except json.JSONDecodeError:
                pass

    os.makedirs(os.path.dirname(output_json), exist_ok=True)

    for idx, artist_name in enumerate(unique_candidates):
        if artist_name in processed_artists:
            continue

        logger.info(f"[{idx + 1}/{len(unique_candidates)}] Extracting Last.fm profile for: {artist_name}")
        
        stats = extract_full_lastfm_feats(network, artist_name)
        enriched_data.append({'primary_artist_name': artist_name, **stats})

        if (idx + 1) % 20 == 0:
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump(enriched_data, f, indent=4)

        time.sleep(0.25)

    with open(output_json, 'w', encoding='utf-8') as f:
        json.dump(enriched_data, f, indent=4)
        
    os.makedirs(os.path.dirname(output_csv), exist_ok=True)
    pd.DataFrame(enriched_data).to_csv(output_csv, index=False)
    
    logger.info(f"Backfill complete! Saved {len(enriched_data)} candidate artists to: {output_csv}")
    
if __name__ == "__main__":

    candidate_tracks = pd.read_csv('../data/processed/clean_data/candidate_tracks.csv')
    backfilled_candidates = pd.read_csv('../data/processed/clean_data/candidate_tracks_lastfm.csv')

    candidate_inference = pd.merge(
        candidate_tracks,
        backfilled_candidates,
        on='primary_artist_name',
        how='left'
    )

    