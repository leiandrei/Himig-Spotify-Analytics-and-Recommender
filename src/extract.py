from dotenv import load_dotenv
from typing import Dict, Any, List
from spotipy.oauth2 import SpotifyOAuth
from logger import log
import pandas as pd
import pylast
import json
import spotipy
import glob
import os

load_dotenv()

# spotify credentials
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
redirect_uri = os.getenv("REDIRECT_URI")

# last fm credentials
api_key = os.getenv("API_KEY")
shared_secret = os.getenv("SHARED_SECRET")

logger = log(__name__)

network = pylast.LastFMNetwork(api_key=api_key, api_secret=shared_secret)
network.enable_rate_limit()

def pagination(sp, initial_results, nested_key=None):

    paging_obj = initial_results[nested_key] if nested_key else initial_results
    item = list(paging_obj.get('items', []))

    while paging_obj.get('next'):
        paging_obj = sp.next(paging_obj)
        item.extend(paging_obj.get('items', []))

    return item

def extract_spotify(client_id: str, client_secret: str, redirect_url: str):

    logger.info("Extracting JSON Data from Spotify API")

    try:
        scope = (
           "user-library-read user-top-read "
           "user-read-recently-played playlist-read-private "
           "user-follow-read"
        )
        
        auth = SpotifyOAuth(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_url,
            scope=scope
        )      

        logger.info("Verifying OAuth from Spotify API") 

        sp = spotipy.Spotify(auth_manager=auth)
        raw_json_data = {}

        # gather my liked tracks
        saved_tracks = sp.current_user_saved_tracks(limit=50)
        raw_json_data['saved_tracks'] = pagination(sp, saved_tracks)

        # gather short/med/long term top tracks
        short = sp.current_user_top_tracks(limit=50, time_range="short_term")
        medium = sp.current_user_top_tracks(limit=50, time_range="medium_term")
        long = sp.current_user_top_tracks(limit=50, time_range="long_term")

        raw_json_data['short_top_tracks'] = pagination(sp, short)
        raw_json_data['med_top_tracks'] = pagination(sp, medium)
        raw_json_data['long_top_tracks'] = pagination(sp, long)

        # user/recently played/followed artists
        user_p =  sp.current_user_playlists(limit=50)
        recents = sp.current_user_recently_played(limit=50)
        followed = sp.current_user_followed_artists(limit=50)

        raw_json_data['user_playlists'] = pagination(sp, user_p)
        raw_json_data['recently_played'] = pagination(sp, recents)
        raw_json_data['followed_artists'] = pagination(sp, followed, nested_key='artists')


        with open('../data/raw/spotify_raw_data.json', 'w', encoding="utf-8") as json_file:
            json.dump(raw_json_data, json_file, indent=4, ensure_ascii=False)

        logger.info("Data extraction and json dump complete.")

    except Exception as e:
        logger.error(f"Error has occured: {e}")
        raise

def normalize_json(directory: str, output_dir: str, record_keys: List[str] = None) -> Dict[str, List[Dict[str, Any]]]:

    try:
        with open(directory, 'r', encoding='utf-8') as json_file:
            data = json.load(json_file)

        normalized = {}

        if not record_keys:
            record_keys = list(data.keys())

        for key in record_keys:
            if key in data and data[key]:
                
                dframe = pd.json_normalize(data[key])
                output_path = os.path.join(output_dir, f"{key}_norm.json")
                dframe.to_json(output_path, orient='records', indent=4)

                logger.info(f"Normalized {key} and saved to: {output_path}")
                normalized[key] = dframe.to_dict(orient='records')

            else:
                logger.warning(f"Key {key} is not found.")

        return normalized
        
    except Exception as e:
        logger.error(f"Unable to normalize JSON data: {e}")
        raise


def get_unique_artists(directory: str) -> List[str]:

    unique_artists = set()

    csv_files = glob.glob(os.path.join(directory, "*.csv"))

    for file in csv_files:

        df = pd.read_csv(file)

        if 'primary_artist_name' in df.columns:
            artists = df['primary_artist_name'].dropna().unique()
            unique_artists.update(artists)

        elif 'name' in df.columns and 'followed_artists' in file:
            artists = df['name'].dropna().unique()
            unique_artists.update(artists)

    logger.info(f"Total unique artists found: {len(unique_artists)}")
    return list(unique_artists)


def lastfm_features_extract(artist_name: str) -> Dict[str, Any]:

    try:
        artist = network.get_artist(artist_name)
        correction = artist.get_correction()

        if correction:
            artist = network.get_artist(correction)

        top_tags_data = artist.get_top_tags(limit=20)
        tags = [tag.item.get_name() for tag in top_tags_data]

        similar_data = artist.get_similar(limit=20)
        similar_artists = [similar.item.get_name() for similar in similar_data]

        logger.info("JSON Data from Last.fm API sucessfully extracted.")
        return {
            "artist" : artist_name, "tags" : tags, "similar_artists" : similar_artists
        }

    except pylast.WSError as e:
        logger.warning(f"Last.fm API Error for {artist_name}: {e}")
        return {"artist": artist_name, "tags": [], "similar_artists": []}

    except Exception as e:
        logger.error(f"Unexpected error fetching data for {artist_name}: {e}")
        return {"artist": artist_name, "tags": [], "similar_artists": []}

if __name__ == "__main__":

    # main orchestration here:

    # call function to extract data
    # extract_spotify(client_id, client_secret, redirect_uri)

    """
        spotify_keys = [
            'saved_tracks', 'short_to   p_tracks',
            'med_top_tracks', 'long_top_tracks',
            'user_playlists', 'recently_played',
            'followed_artists']

        normalized_data = normalize_json(
            directory='../data/raw/spotify_raw_data.json',
            output_dir='../data/raw/',
            record_keys=spotify_keys
        )
    """

    processed_dir = '../data/processed/csv'
    output_file = '../data/raw/jsons/lastfm_features.json'

    artist_lists = get_unique_artists(processed_dir)

    enriched_data = []

    if os.path.exists(output_file):

        with open(output_file, 'r', encoding='utf-8') as file:
            try:
                enriched_data = json.load(file)
                logger.info(f"Loaded {len(enriched_data)} previously processed artists.")
            except:
                logger.warning("Can't open the existing JSON File.")

    processed_artists = {d['artist'] for d in enriched_data}
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    for idx, artist in enumerate(artist_lists):
        if artist in processed_artists:
            continue

        artist_features = lastfm_features_extract(artist)
        enriched_data.append(artist_features)

        if (idx + 1) % 50 == 0:
            with open(output_file, 'w', encoding='utf-8') as file:
                json.dump(enriched_data, file, indent=4)

            logger.info("JSON Data safely saved onto a disk.")

    with open(output_file, 'w', encoding='utf-8') as file:
        json.dump(enriched_data, file, indent=4)

    logger.info(f"JSON Data from Last.fm has been sucessfully orchestrated, saved to: {output_file}")





    
    
    