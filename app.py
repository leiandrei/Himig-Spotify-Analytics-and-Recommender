import html
import os
import re
from collections import Counter

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from scipy.sparse import load_npz

APP_NAME = "Himig"
APP_TAGLINE = "A Spotify Analytics with a Content-based Recommender System"

st.set_page_config(page_title=f"{APP_NAME} | {APP_TAGLINE}", page_icon="🎵", layout="wide")

GREEN, GREEN_DARK, GREY = "#1DB954", "#168D40", "#B3B3B3"
GREENS = ["#1DB954", "#1ED760", "#169C46", "#14833B", "#0E6B30"]
INTERACTION_WEIGHTS = {"Long Top Track": 1.0, "Saved": 0.8, "Recently Played": 0.25}

NON_GENRE = {
    "american", "british", "canadian", "australian", "swedish", "german", "french", "irish",
    "scottish", "japanese", "korean", "uk", "usa", "seen live", "favorites", "favourite",
    "male vocalists", "female vocalists", "male vocalist", "female vocalist", "singer",
    "legend", "awesome", "good", "beautiful", "love", "cool",
}
DECADE_RE = re.compile(r"^(\d{2}|\d{4})s$")

st.markdown(
    f"""
<style>
    .stApp {{ background-color: #121212; color: #FFFFFF; }}
    section[data-testid="stSidebar"] {{ background-color: #000000; border-right: 1px solid #282828; }}
    h1, h2, h3, h4 {{ color: #FFFFFF !important; font-weight: 700; }}
    .spotify-green {{ color: {GREEN} !important; font-weight: 900; }}
    .hero {{ padding: 8px 0 18px 0; }}
    .hero-title {{ font-size: 3.2rem; font-weight: 900; letter-spacing: -1px; line-height: 1.05;
        background: linear-gradient(90deg, {GREEN}, #A8F0C0); -webkit-background-clip: text;
        -webkit-text-fill-color: transparent; }}
    .hero-sub {{ color: {GREY}; font-size: 1.05rem; margin-top: 4px; }}
    .section-title {{ font-size: 1.25rem; font-weight: 700; margin: 28px 0 4px 0; }}
    .section-sub {{ color: {GREY}; font-size: 0.9rem; margin-bottom: 12px; }}
    .metric-card {{ background-color: #181818; padding: 20px; border-radius: 10px; height: 100%;
        transition: background-color 0.25s ease, transform 0.25s ease; border: 1px solid #222; }}
    .metric-card:hover {{ background-color: #242424; transform: translateY(-2px); }}
    .metric-title {{ font-size: 1.15rem; font-weight: 700; margin-bottom: 8px; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis; }}
    .spot-label {{ color: {GREY}; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 1.2px; font-weight: 700; }}
    .spot-value {{ font-size: 1.6rem; font-weight: 800; margin: 6px 0 2px 0; white-space: nowrap;
        overflow: hidden; text-overflow: ellipsis; }}
    .spot-note {{ color: {GREY}; font-size: 0.85rem; }}
    .rank-badge {{ background: {GREEN}; color: #000; font-weight: 800; border-radius: 50%; width: 26px; height: 26px;
        display: inline-flex; align-items: center; justify-content: center; font-size: 0.8rem; margin-right: 8px; }}
    div[data-testid="stMetricValue"] {{ color: {GREEN}; }}
    div[data-testid="stMetric"] {{ background-color: #181818; padding: 14px 18px; border-radius: 10px; border: 1px solid #222; }}
    .tag-pill {{ background-color: {GREEN}; border-radius: 12px; padding: 2px 10px; font-size: 0.72rem;
        font-weight: 600; margin-right: 6px; margin-bottom: 6px; display: inline-block; color: #000; text-transform: capitalize; }}
    .stats-row {{ display: flex; justify-content: space-between; font-size: 0.85rem; color: {GREY}; margin-top: 14px; font-weight: 500; }}
    .because {{ color: {GREY}; font-size: 0.8rem; margin-top: 10px; line-height: 1.35; }}
    .because b {{ color: #FFFFFF; font-weight: 600; }}
    .match-bar {{ height: 4px; background: #2A2A2A; border-radius: 2px; margin-top: 10px; }}
    .match-fill {{ height: 4px; background: {GREEN}; border-radius: 2px; }}
    .step-card {{ background: #181818; border-left: 3px solid {GREEN}; padding: 14px 16px; border-radius: 6px; height: 100%; }}
    .step-card b {{ color: {GREEN}; }}
    .stTabs [data-baseweb="tab-list"] {{ background-color: #121212; gap: 24px; }}
    .stTabs [data-baseweb="tab"] {{ color: {GREY}; font-weight: 600; font-size: 1rem; }}
    .stTabs [aria-selected="true"] {{ color: #FFFFFF; border-bottom-color: {GREEN}; }}
</style>
""",
    unsafe_allow_html=True,
)

def show(fig):
    try:
        st.plotly_chart(fig, width="stretch")
    except TypeError:
        st.plotly_chart(fig, use_container_width=True)


def style(fig, height=380, title=None):
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=height, margin=dict(l=10, r=10, t=50 if title else 20, b=10),
        font=dict(color="#E0E0E0"), coloraxis_showscale=False,
        title=dict(text=title, font=dict(size=16)) if title else None,
    )
    return fig


def trunc(s, n=28):
    s = str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def section(title, sub=""):
    st.markdown(f'<div class="section-title">{title}</div><div class="section-sub">{sub}</div>', unsafe_allow_html=True)


def spotlight(label, value, note):
    st.markdown(
        f'<div class="metric-card"><div class="spot-label">{label}</div>'
        f'<div class="spot-value">{html.escape(str(value))}</div><div class="spot-note">{html.escape(str(note))}</div></div>',
        unsafe_allow_html=True,
    )


def valid_genres(tags, artist_name, limit=5):
    out, name = [], str(artist_name).lower()
    for t in tags.split(","):
        t = t.strip().lower()
        if t and t != name and t not in NON_GENRE and not DECADE_RE.match(t) and t not in out:
            out.append(t)
        if len(out) == limit:
            break
    return out

@st.cache_data
def load_data():
    base = os.path.dirname(__file__)
    d_tracks = pd.read_csv(os.path.join(base, "data/processed/to_db/dim_tracks.csv"))
    d_artists = pd.read_csv(os.path.join(base, "data/processed/to_db/dim_artists.csv"))
    f_inter = pd.read_csv(os.path.join(base, "data/processed/to_db/fact_interactions.csv"))
    all_a = pd.read_csv(os.path.join(base, "notebooks/analysis/all_artists.csv")).fillna({"tags": "", "similar_artists": ""})

    if "artists_id" not in all_a.columns:
        all_a = all_a.merge(d_artists[["primary_artist_name", "artists_id"]], on="primary_artist_name", how="left")

    all_a["artists_id"] = all_a["artists_id"].astype("Int64")
    all_a["tag_list"] = all_a.apply(lambda r: [t.strip().lower() for t in r["tags"].split(",") if t.strip()], axis=1)
    all_a["n_tags"] = all_a["tag_list"].apply(len)
    cand = all_a["source"] != "library"
    all_a["pop_pct"] = all_a["artist_listeners"].where(cand).rank(pct=True)

    d_tracks["release_date"] = pd.to_datetime(d_tracks["release_date"], errors="coerce")
    feats = load_npz(os.path.join(base, "notebooks/analysis/feature_matrix.npz")).tocsr()
    return d_tracks, d_artists, f_inter, all_a, feats


@st.cache_data
def build_scores(_f_inter, _d_tracks, _all_a, _feats):
    inter = _f_inter.merge(_d_tracks[["track_id", "artists_id"]], on="track_id", how="left")
    inter["weight"] = inter["interaction_type"].map(INTERACTION_WEIGHTS).fillna(0.5)
    signal = inter.groupby("artists_id")["weight"].sum()

    is_lib = (_all_a["source"] == "library").to_numpy()
    lib_rows = np.where(is_lib)[0]

    w_all = np.zeros(len(_all_a))
    w_all[lib_rows] = 1 + np.log1p(_all_a.loc[is_lib, "artists_id"].map(signal).fillna(0).to_numpy(dtype=float))

    profile = np.asarray(_feats[lib_rows].multiply(w_all[lib_rows].reshape(-1, 1)).sum(axis=0)).ravel()
    if np.linalg.norm(profile) > 0:
        profile = profile / np.linalg.norm(profile)
    scores = np.asarray(_feats @ profile).ravel()
    return scores, is_lib, w_all


@st.cache_data
def build_analytics(_d_tracks, _d_artists, _f_inter, _all_a, _w_all, _is_lib):
    inter = _f_inter.copy()
    inter["weight"] = inter["interaction_type"].map(INTERACTION_WEIGHTS).fillna(0.5)

    tracks = _d_tracks.merge(_d_artists[["artists_id", "primary_artist_name"]], on="artists_id", how="left")
    t_score = inter.groupby("track_id").agg(score=("weight", "sum"), n_inter=("weight", "size"))
    tracks = tracks.merge(t_score, on="track_id", how="left").fillna({"score": 0, "n_inter": 0})
    tracks["label"] = tracks["song_name"].str.replace(r"\s*-\s*(Bonus Track|Remaster.*|\d{4} Remaster.*)$", "", regex=True)
    tracks["year"] = tracks["release_date"].dt.year
    tracks["decade"] = (tracks["year"] // 10 * 10).astype("Int64")
    lib = _all_a[_is_lib].copy()
    lib["taste_weight"] = _w_all[_is_lib]
    a_stats = tracks.groupby("artists_id").agg(n_tracks=("track_id", "nunique"), signal=("score", "sum"))
    lib = lib.merge(a_stats, left_on="artists_id", right_index=True, how="left").fillna({"n_tracks": 0, "signal": 0})

    rows = []
    for name, tags, w in zip(lib["primary_artist_name"], lib["tags"], lib["taste_weight"]):
        for g in valid_genres(tags, name):
            rows.append((g, w))
    genres = pd.DataFrame(rows, columns=["genre", "weight"]).groupby("genre").agg(
        weight=("weight", "sum"), artists=("weight", "size")).sort_values("weight", ascending=False).reset_index()
    return tracks, lib, genres


def generate_recommendations(scores, is_lib, all_a, n_items, genre, pop_range):
    s = scores.astype(float).copy()
    s[is_lib] = -np.inf
    s[all_a["n_tags"].to_numpy() < 3] = -np.inf
    if genre:
        s[~all_a["tag_list"].apply(lambda l: genre in l).to_numpy()] = -np.inf
    pct = all_a["pop_pct"].to_numpy()
    s[(pct < pop_range[0] / 100) | (pct > pop_range[1] / 100)] = -np.inf

    top_idx = np.argsort(-s)[:n_items]
    top_idx = top_idx[np.isfinite(s[top_idx])]
    res = all_a.iloc[top_idx].copy()
    res["score"] = s[top_idx]
    return res


def explain(row, lib_lookup):
    sims = [x.strip().lower() for x in row["similar_artists"].split(",") if x.strip()]
    hits = [lib_lookup[x] for x in sims if x in lib_lookup]
    hits.sort(key=lambda h: -h[1])
    return [h[0] for h in hits[:3]]

with st.spinner("Analyzing listening profile..."):
    dim_tracks, dim_artists, fact_inter, all_artists, feature_matrix = load_data()
    scores, is_lib, w_all = build_scores(fact_inter, dim_tracks, all_artists, feature_matrix)
    tracks_df, lib_df, genres_df = build_analytics(dim_tracks, dim_artists, fact_inter, all_artists, w_all, is_lib)

st.sidebar.markdown(f'<h2 class="spotify-green">🎵 {APP_NAME}</h2>', unsafe_allow_html=True)
page = st.sidebar.radio("Navigate", ["🏠 Home", "🎧 Recommender", "📚 Library Explorer"], label_visibility="collapsed")
st.sidebar.markdown("---")
st.sidebar.caption(
    f"{is_lib.sum():,} library artists · {len(dim_tracks):,} tracks · {len(fact_inter):,} interactions"
)

st.markdown(
    f'<div class="hero"><div class="hero-title">{APP_NAME}</div><div class="hero-sub">{APP_TAGLINE}</div></div>',
    unsafe_allow_html=True,
)

if page == "🏠 Home":
    hours = tracks_df.loc[tracks_df["n_inter"] > 0, "duration_min"].sum() / 60
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Library Artists", f"{is_lib.sum():,}")
    c2.metric("Tracks", f"{len(dim_tracks):,}")
    c3.metric("Interactions", f"{len(fact_inter):,}")
    c4.metric("Hours of Music", f"{hours:,.1f}")
    c5.metric("Genres Explored", f"{len(genres_df):,}")

    top_g = genres_df.head(5)
    top_a = lib_df.sort_values(["taste_weight", "artist_listeners"], ascending=False).head(5)
    top_t = tracks_df.sort_values(["score", "n_inter"], ascending=False).head(5)

    section("Your #1s", "The genre, artist and track that define your library.")
    s1, s2, s3 = st.columns(3)
    with s1:
        spotlight("Top Genre", top_g.iloc[0]["genre"].title(), f"{int(top_g.iloc[0]['artists'])} artists in your library")
    with s2:
        spotlight("Top Artist", top_a.iloc[0]["primary_artist_name"], f"{int(top_a.iloc[0]['n_tracks'])} tracks in your library")
    with s3:
        spotlight("Top Track", top_t.iloc[0]["label"], f"by {top_t.iloc[0]['primary_artist_name']}")

    section("Your Top 5s", "Ranked by interaction strength: Long Top Track = 1.0, Saved = 0.8, Recently Played = 0.25.")
    g_col, a_col, t_col = st.columns(3)
    with g_col:
        d = top_g.assign(label=top_g["genre"].str.title())
        fig = px.bar(d, x="weight", y="label", orientation="h", text=d["weight"].round(1),
                     color="weight", color_continuous_scale=["#0E6B30", GREEN])
        fig.update_yaxes(autorange="reversed", title=None)
        fig.update_xaxes(title="Taste weight", showgrid=False)
        fig.update_traces(textposition="outside", cliponaxis=False)
        show(style(fig, 320, "Top 5 Genres"))
    with a_col:
        fig = px.bar(top_a, x="taste_weight", y="primary_artist_name", orientation="h",
                     text=top_a["taste_weight"].round(2), color="taste_weight",
                     color_continuous_scale=["#0E6B30", GREEN], hover_data={"n_tracks": True, "artist_listeners": ":,"})
        fig.update_yaxes(autorange="reversed", title=None)
        fig.update_xaxes(title="Taste weight", showgrid=False)
        fig.update_traces(textposition="outside", cliponaxis=False)
        show(style(fig, 320, "Top 5 Artists"))
    with t_col:
        d = top_t.assign(short=top_t["label"].map(lambda x: trunc(x, 26)))
        fig = px.bar(d, x="score", y="short", orientation="h", text=d["score"].round(1),
                     color="score", color_continuous_scale=["#0E6B30", GREEN],
                     hover_data={"primary_artist_name": True, "album_name": True, "short": False})
        fig.update_yaxes(autorange="reversed", title=None)
        fig.update_xaxes(title="Interaction score", showgrid=False)
        fig.update_traces(textposition="outside", cliponaxis=False)
        show(style(fig, 320, "Top 5 Tracks"))

    section("Taste Landscape", "Where your library sits across genres and eras.")
    left, right = st.columns([3, 2])
    with left:
        d = genres_df.head(20).assign(label=lambda x: x["genre"].str.title())
        fig = px.treemap(d, path=["label"], values="weight", color="weight",
                         color_continuous_scale=["#0B3D1E", GREEN])
        fig.update_traces(textinfo="label+percent root", hovertemplate="%{label}<br>weight %{value:.1f}<extra></extra>")
        show(style(fig, 400, "Genre Map (Top 20)"))
    with right:
        dec = tracks_df.dropna(subset=["decade"]).groupby("decade").size().reset_index(name="tracks")
        dec["decade"] = dec["decade"].astype(int).astype(str) + "s"
        fig = px.bar(dec, x="decade", y="tracks", color="tracks", color_continuous_scale=["#0E6B30", GREEN])
        fig.update_xaxes(title=None, type="category")
        fig.update_yaxes(title="Tracks", showgrid=False)
        show(style(fig, 400, "Tracks by Release Decade"))

    left, right = st.columns(2)
    with left:
        mix = fact_inter["interaction_type"].value_counts().reset_index()
        mix.columns = ["type", "count"]
        fig = px.pie(mix, names="type", values="count", hole=0.6,
                     color_discrete_sequence=[GREEN, "#1ED760", "#535353"])
        fig.update_traces(textinfo="percent+label")
        fig.update_layout(showlegend=False)
        show(style(fig, 360, "How You Listen"))
    with right:
        fig = px.histogram(tracks_df, x="duration_min", nbins=30, color_discrete_sequence=[GREEN])
        fig.add_vline(x=tracks_df["duration_min"].median(), line_dash="dash", line_color="#FFFFFF",
                      annotation_text=f"median {tracks_df['duration_min'].median():.1f} min")
        fig.update_xaxes(title="Track length (min)")
        fig.update_yaxes(title="Tracks", showgrid=False)
        show(style(fig, 360, "Track Length Distribution"))

    section("Mainstream vs. Niche", "Every artist by Last.fm reach. Green = your library, grey = the discovery pool.")
    fig = px.scatter(all_artists, x="artist_listeners", y="artist_playcount", color="source",
                     log_x=True, log_y=True, hover_name="primary_artist_name", opacity=0.7,
                     color_discrete_map={"library": GREEN, "candidate": "#6B6B6B"})
    fig.update_xaxes(title="Listeners (log)")
    fig.update_yaxes(title="Playcount (log)")
    fig.update_layout(legend_title=None, legend=dict(orientation="h", y=1.08))
    show(style(fig, 460))

elif page == "🎧 Recommender":
    section("How the Recommender Works", "Content-based filtering: it matches artist features, not other people's listening.")
    steps = [
        ("1 · Weight", "Each library artist gets a taste weight from your interactions (Long Top Track 1.0, Saved 0.8, Recently Played 0.25), log-scaled."),
        ("2 · Profile", "Artist feature vectors are combined, weighted by taste, into one normalized taste-profile vector."),
        ("3 · Score", "Every artist outside your library is scored by cosine similarity to that profile."),
        ("4 · Filter", "Library artists and thinly-tagged artists (under 3 tags) are removed; your filters are applied; top N are shown."),
    ]
    for col, (title, text) in zip(st.columns(4), steps):
        col.markdown(f'<div class="step-card"><b>{title}</b><br><span style="color:{GREY};font-size:0.85rem">{text}</span></div>', unsafe_allow_html=True)

    section("Tune Your Discovery")
    cand_tags = Counter(g for tl, n in zip(all_artists["tag_list"][~is_lib], all_artists["primary_artist_name"][~is_lib])
                        for g in valid_genres(", ".join(tl), n, limit=10))
    genre_opts = [g for g, c in cand_tags.most_common() if c >= 8]

    f1, f2, f3 = st.columns([2, 2, 3])
    sel = f1.selectbox("Vibe filter", ["All"] + genre_opts, format_func=lambda x: x.title())
    n_recos = f2.slider("Number of candidates", 4, 40, 12, step=4)
    pop_range = f3.slider("Popularity (0 = underground, 100 = mainstream)", 0, 100, (0, 100))

    recos = generate_recommendations(scores, is_lib, all_artists, n_recos, None if sel == "All" else sel, pop_range)

    if recos.empty:
        st.warning("No candidates match these filters. Try a different vibe or widen the popularity range.")
    else:
        lib_lookup = {n.lower(): (n, w) for n, w in zip(all_artists.loc[is_lib, "primary_artist_name"], w_all[is_lib])}

        t1, t2 = st.tabs(["🎧 Recommended for You", "🔬 Why These Picks"])
        with t1:
            best = recos["score"].max()
            cols = st.columns(4)
            for i, (_, row) in enumerate(recos.iterrows()):
                tags_html = "".join(f'<span class="tag-pill">{html.escape(t)}</span>' for t in row["tag_list"][:3])
                because = explain(row, lib_lookup)
                because_html = (f'<div class="because">Because you listen to <b>{html.escape(", ".join(because))}</b></div>'
                                if because else '<div class="because">Matched on overall taste profile</div>')
                pct = max(row["score"], 0) * 100
                with cols[i % 4]:
                    st.markdown(
                        f"""
                        <div class="metric-card">
                            <div class="metric-title"><span class="rank-badge">{i + 1}</span>{html.escape(row['primary_artist_name'])}</div>
                            <div style="min-height: 50px;">{tags_html}</div>
                            <div class="stats-row"><span>👥 {int(row['artist_listeners']):,}</span><span>{pct:.1f}% Match</span></div>
                            <div class="match-bar"><div class="match-fill" style="width:{min(pct / (best * 100) * 100, 100):.0f}%"></div></div>
                            {because_html}
                        </div><br>
                        """,
                        unsafe_allow_html=True,
                    )
            export = recos[["primary_artist_name", "score", "artist_listeners", "tags"]].rename(
                columns={"primary_artist_name": "artist", "score": "match"})
            st.download_button("⬇️ Download recommendations (CSV)", export.to_csv(index=False), "himig_recommendations.csv", "text/csv")

        with t2:
            left, right = st.columns(2)
            with left:
                d = recos.assign(match=recos["score"] * 100, name=recos["primary_artist_name"].map(lambda x: trunc(x, 24)))
                fig = px.bar(d, x="match", y="name", orientation="h", color="match",
                             color_continuous_scale=["#0E6B30", GREEN])
                fig.update_yaxes(autorange="reversed", title=None)
                fig.update_xaxes(title="Match %", showgrid=False)
                show(style(fig, max(340, 26 * len(d) + 80), "Match Score by Candidate"))
            with right:
                prof = genres_df.head(8)
                rec_g = Counter(g for tl, n in zip(recos["tag_list"], recos["primary_artist_name"])
                                for g in valid_genres(", ".join(tl), n))
                tot_rec = sum(rec_g.values()) or 1
                cmp_df = pd.DataFrame({
                    "genre": prof["genre"].str.title(),
                    "Your library": prof["weight"] / genres_df["weight"].sum() * 100,
                    "Recommendations": [rec_g.get(g, 0) / tot_rec * 100 for g in prof["genre"]],
                }).melt("genre", var_name="set", value_name="share")
                fig = px.bar(cmp_df, x="genre", y="share", color="set", barmode="group",
                             color_discrete_map={"Your library": GREEN, "Recommendations": "#7A7A7A"})
                fig.update_xaxes(title=None)
                fig.update_yaxes(title="Share of genre tags (%)", showgrid=False)
                fig.update_layout(legend_title=None, legend=dict(orientation="h", y=1.12))
                show(style(fig, 420, "Taste Profile vs. Recommendations"))

            pool = all_artists[~is_lib].assign(group="Discovery pool")
            picks = all_artists.loc[recos.index].assign(group="Recommended")
            fig = px.scatter(pd.concat([pool, picks]), x="artist_listeners", y="artist_playcount", color="group",
                             log_x=True, log_y=True, hover_name="primary_artist_name",
                             color_discrete_map={"Discovery pool": "#4A4A4A", "Recommended": GREEN})
            fig.update_traces(marker=dict(size=7, opacity=0.8))
            fig.update_xaxes(title="Listeners (log)")
            fig.update_yaxes(title="Playcount (log)")
            fig.update_layout(legend_title=None, legend=dict(orientation="h", y=1.08))
            show(style(fig, 420, "Where Recommendations Sit in the Discovery Pool"))

else:
    section("Library Explorer", "Every artist in your library with the taste weight the recommender learned from.")
    q = st.text_input("Search artist or genre", placeholder="e.g. kendrick, indie rock")
    table = lib_df.assign(genres=lib_df["tag_list"].map(lambda l: ", ".join(l[:5])))
    if q:
        mask = (table["primary_artist_name"].str.contains(q, case=False, regex=False)
                | table["genres"].str.contains(q, case=False, regex=False))
        table = table[mask]
    table = table.sort_values("taste_weight", ascending=False)[
        ["primary_artist_name", "taste_weight", "n_tracks", "artist_listeners", "genres"]]
    table.columns = ["Artist", "Taste weight", "Tracks", "Listeners", "Top tags"]
    st.caption(f"{len(table):,} artists")
    st.dataframe(
        table, hide_index=True, height=560,
        column_config={
            "Taste weight": st.column_config.ProgressColumn(
                "Taste weight", min_value=0.0, max_value=float(max(table["Taste weight"].max(), 1)) if len(table) else 1.0, format="%.2f"),
            "Listeners": st.column_config.NumberColumn(format="%d"),
            "Tracks": st.column_config.NumberColumn(format="%d"),
        },
    )