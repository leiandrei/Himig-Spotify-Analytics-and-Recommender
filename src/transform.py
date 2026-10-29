from typing import Dict, List, Any
from logger import log
import pandas as pd
import json
import os

logger = log(__name__)

def clean_followed_artists(filepath: str, output_path: str) -> None:
    df = pd.read_json(filepath)

    if 'images' in df.columns:
        df['image_url'] = df['images'].apply(
            lambda x: x[0]['url'] if isinstance(x, list) and len(x) > 0 else None
        )

    if 'genres' in df.columns:
        df['genres'] = df['genres'].apply(
            lambda x: ", ".join(x) if isinstance(x, list) and len(x) > 0 else None
        )

    rename_map = { 'followers.total' : 'total_followers' }

    df = df.rename(columns=rename_map)

    columns_to_drop = [
        'images', 'href', 'uri', 'type',
        'external_urls.spotify', 'followers.href'
    ]

    existing = [col for col in columns_to_drop if col in df.columns]
    df = df.drop(columns=existing)

    logger.info(f"Unnecessary columns dropped: {existing}")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"Raw CSV successfully cleaned and saved to: {output_path}")

def clean_spotify_tracks(filepath: str, output_path: str, is_wrapped: bool = False) -> None:

    df = pd.read_json(filepath)

    if is_wrapped:
        df.columns = [col.replace('track.', '') if col.startswith('track.') else col for col in df.columns]

    if 'artists' in df.columns:
        df['primary_artist_name'] = df['artists'].apply(
            lambda x: x[0]['name'] if isinstance(x, list) and len(x) > 0 else None
        )

        df['primary_artist_id'] = df['artists'].apply(
            lambda x: x[0]['id'] if isinstance(x, list) and len(x) > 0 else None
        )

        df['all_artists'] = df['artists'].apply(
            lambda x: ", ".join([artist['name'] for artist in x]) if isinstance(x, list) else None
        )

    if 'album.images' in df.columns:
        df['album_image_url'] = df['album.images'].apply(
            lambda x: x[0]['url'] if isinstance(x, list) and len(x) > 0 else None
        )

    columns_to_drop = [
        'artists', 'album.images', 'album.artists', 'available_markets', 
        'album.available_markets', 'href', 'uri', 'track_href', 'type', 
        'external_urls.spotify', 'album.external_urls.spotify'
    ]

    existing = [col for col in columns_to_drop if col in df.columns]
    df = df.drop(columns=existing)

    logger.info(f"Unnecessary columns dropped: {existing}")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"Raw CSV successfully cleaned and saved to: {output_path}")
    

def clean_playlists(filepath: str, output_path: str) -> None:

    df = pd.read_json(filepath)

    if 'images' in df.columns:
        df['image_url'] = df['images'].apply(
            lambda x: x[0]['url'] if isinstance(x, list) and len(x) > 0 else None
        )

    rename_map = {
        'owner.display_name' : 'owner_name',
        'owner.id' : 'owner_id',
        'tracks.total' : 'total_tracks'
    }

    df = df.rename(columns=rename_map)

    columns_to_drop = [
        'images', 'href', 'uri', 'type', 'external_urls.spotify', 
        'owner.href', 'owner.uri', 'owner.type', 'owner.external_urls.spotify', 
        'tracks.href'
    ]

    existing = [col for col in columns_to_drop if col in df.columns]
    df = df.drop(columns=existing)

    logger.info(f"Unnecessary columns dropped: {existing}")
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"Raw CSV successfully cleaned and saved to: {output_path}")


def drop_cols(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    return df.drop(columns=cols)


def clean_lastfm_feats(filepath: str, output_path: str) -> None:

    try:
        df = pd.read_json(filepath)

        if 'tags' in df.columns:
            df['tags'] = df['tags'].apply(
                lambda x: ", ".join(x) if isinstance(x, list) else None
            )

        if 'similar_artists' in df.columns:
            df['similar_artists'] = df['similar_artists'].apply(
                lambda x: ", ".join(x) if isinstance(x, list) else None
            )

        df = df.dropna(subset=['tags', 'similar_artists'], how='all')

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info(f"Cleaned Last.Fm features successfully transformed to: {output_path}")

    except Exception as e:
        logger.error(f"Unable to transform Last.Fm features: {e}")

def clean_candidate_tracks(filepath: str, output_path: str) -> pd.DataFrame:

    try:

        if not os.path.exists(filepath):
            logger.error(f"Raw JSON Path not found. Try Again.")
            return pd.DataFrame()

        with open(filepath, 'r', encoding='utf-8') as json_file:
            data = json.load(json_file)

        df = pd.DataFrame(data)

        if df.empty:
            logger.error(f"The DataFrame is Empty")
            return pd.DataFrame()

        init_count = len(df)

        df = df.drop_duplicates(subset=['id']).reset_index(drop=True)
        logger.info(f"Deduplicated Tracks: {init_count} -> {df.shape[0]} rows")
        df = df.dropna(subset=['id', 'name', 'primary_artist_name'])

        df['explicit'] = df['explicit'].astype('int32')

        text_cols = ['name', 'album_name', 'primary_artist_name', 'all_artists']

        for cols in text_cols:
            if cols in df.columns:
                df[cols] = df[cols].astype(str).str.strip()

        ordered_cols = ['id', 'name', 'primary_artist_name', 'primary_artist_id', 'all_artists',
                        'album_name', 'release_date', 'release_year', 'duration_ms', 'explicit',
                        'explicit_album_url']

        df = df[[col for col in ordered_cols if col in df.columns]]

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)
        logger.info(f"Cleaned candidate tracks saved ({len(df)} records) to: {output_path}")

        return df

    except Exception as e:
        logger.error(f"Unexpected Error Occured: {e}")
        raise

    
        




    
if __name__ == "__main__":

    # main orchestration of transformations
    """
    clean_followed_artists(
        filepath='../data/raw/jsons/followed_artists_norm.json',
        output_path='../data/raw/csv/followed_artists.csv'
    )

    clean_playlists(
        filepath='../data/raw/jsons/user_playlists_norm.json',
        output_path='../data/raw/csv/user_playlists.csv'
    )

    tracks_ = ['short_top_tracks', 'med_top_tracks', 'long_top_tracks']

    for track in tracks_:
        clean_spotify_tracks(
            filepath=f'../data/raw/jsons/{track}_norm.json',
            output_path=f'../data/raw/csv/{track}.csv',
            is_wrapped=False
        )

    wrapped_tracks = ['saved_tracks', 'recently_played']

    for tracks in wrapped_tracks:
        clean_spotify_tracks(
            filepath=f'../data/raw/jsons/{tracks}_norm.json',
            output_path=f'../data/raw/csv/{tracks}.csv',
            is_wrapped=True
        )
    """


    """
    clean_lastfm_feats(
        filepath='../data/raw/jsons/lastfm_features.json',
        output_path='../data/raw/csv/lastfm_features.csv'
    )
    """

    clean_candidate_tracks(
        filepath='../data/raw/jsons/candidate_tracks_raw.json',
        output_path='../data/raw/csv/candidate_tracks.csv'
    )

    
    

