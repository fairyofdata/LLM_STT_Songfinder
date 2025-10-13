import os
import uvicorn
import json
import faiss
import numpy as np
import openai
from sentence_transformers import SentenceTransformer
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Response, Form
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from logging import getLogger, basicConfig, INFO
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from itsdangerous import URLSafeSerializer
from pydantic import BaseModel, Field, AliasChoices
from typing import List, Dict, Any
from collections import defaultdict
import ast
from pydub import AudioSegment
import io

basicConfig(level=INFO)
logger = getLogger(__name__)

# --- Pydantic Models with new naming convention ---
class PlaylistSongRequest(BaseModel):
    artist: str
    songTitle: str
    songDescription: str
    tagName: List[str]

class PlaylistDetailsRequest(BaseModel):
    songs: List[PlaylistSongRequest]

class PlaylistCreationRequest(BaseModel):
    songIds: List[str] = Field(..., validation_alias=AliasChoices('songIds', 'song_ids'))
    title: str = Field(..., description="The title for the new playlist.")
    description: str = Field(..., description="The description for the new playlist.")


SECRET_KEY = os.getenv("APP_SECRET_KEY", "a_default_secret_key_for_local_testing")
serializer = URLSafeSerializer(SECRET_KEY)
SESSION_COOKIE_NAME = "spotify-session"

logger.info("서버 시작... 모델 및 데이터베이스를 로드합니다.")
embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
try:
    with open('line_metadata.json', 'r', encoding='utf-8') as f:
        line_metadata = json.load(f)
    with open('song_metadata.json', 'r', encoding='utf-8') as f:
        song_metadata = json.load(f)
    
    line_embeddings = np.load('line_embeddings.npy')
    song_embeddings = np.load('song_embeddings.npy')
    summary_embeddings = np.load('summary_embeddings.npy')

    line_index = faiss.IndexFlatIP(line_embeddings.shape[1])
    line_index.add(line_embeddings)
    
    song_index = faiss.IndexFlatIP(song_embeddings.shape[1])
    song_index.add(song_embeddings)
    
    summary_index = faiss.IndexFlatIP(summary_embeddings.shape[1])
    summary_index.add(summary_embeddings)

    lines_by_song_idx = defaultdict(list)
    for i, meta in enumerate(line_metadata):
        lines_by_song_idx[meta['original_song_index']].append(i)

    logger.info(f"DB 로드 완료. {len(song_metadata)}곡, {len(line_metadata)}개의 라인, {len(summary_embeddings)}개의 요약문이 준비되었습니다.")

except Exception as e:
    logger.error(f"DB 로딩 실패: {e}", exc_info=True)
    line_index, song_index, summary_index = None, None, None

REDIRECT_URI = "https://fairyofdata-jpop-stt-module.hf.space/callback"
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=REDIRECT_URI,
    scope="streaming user-read-private user-read-email user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-modify-public playlist-modify-private")

api_key = os.getenv("openai")
client = openai.OpenAI(api_key=api_key) if api_key else None

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

def parse_tags(tags_str: str) -> List[str]:
    if not isinstance(tags_str, str) or not tags_str.startswith('['):
        return []
    try:
        return ast.literal_eval(tags_str)
    except (ValueError, SyntaxError):
        return []

def search_pipeline_from_text(query_text: str) -> (Dict[str, Any], str, List[Dict[str, Any]]):
    if song_index is None:
        return None, "", []
    
    query_vector = embedder.encode([query_text]).astype('float32')
    faiss.normalize_L2(query_vector)

    D_summary, I_summary = summary_index.search(query_vector, 1)
    D_lyric, I_lyric = line_index.search(query_vector, 1)
    
    identified_song_idx = -1
    matched_lyric = ""
    
    summary_score = D_summary[0][0] if D_summary.size > 0 else 0
    lyric_score = D_lyric[0][0] if D_lyric.size > 0 else 0

    if summary_score > 0.4 or lyric_score > 0.4:
        if summary_score > lyric_score:
            identified_song_idx = line_metadata[I_summary[0][0]]['original_song_index']
            matched_lyric = song_metadata[identified_song_idx].get('summary', 'N/A')
        else:
            identified_song_idx = line_metadata[I_lyric[0][0]]['original_song_index']
            matched_lyric = line_metadata[I_lyric[0][0]]['line_text']
    else:
        return None, "", []

    raw_identified_song = song_metadata[identified_song_idx]
    identified_song = {
        "songId": raw_identified_song.get('spotify_id'),
        "songTitle": raw_identified_song.get('title'),
        "artist": raw_identified_song.get('artist'),
        "albumCoverUrl": raw_identified_song.get('album_cover_url'),
        "tagName": parse_tags(raw_identified_song.get('tags_normalized', '[]')),
        "songDescription": raw_identified_song.get('summary', 'N/A'),
        "userQuery": query_text
    }

    song_vector = song_embeddings[identified_song_idx:identified_song_idx+1]
    
    candidate_scores = defaultdict(float)
    recommendation_reasons = defaultdict(list)

    D_song, I_song = song_index.search(song_vector, 10)
    for i, idx in enumerate(I_song[0]):
        candidate_scores[idx] += D_song[0][i] * 0.5
        recommendation_reasons[idx].append("분위기와 장르가 비슷해요.")

    summary_vector = summary_embeddings[identified_song_idx:identified_song_idx+1]
    D_summary, I_summary = summary_index.search(summary_vector, 10)
    for i, idx in enumerate(I_summary[0]):
        candidate_scores[idx] += D_summary[0][i] * 0.3
        recommendation_reasons[idx].append("곡의 전반적인 감성이 비슷해요.")

    original_tags = set(identified_song['tagName'])
    for idx in list(candidate_scores.keys()):
        candidate_tags = set(parse_tags(song_metadata[idx].get('tags_normalized', '[]')))
        if original_tags.intersection(candidate_tags):
            candidate_scores[idx] += 0.2
            recommendation_reasons[idx].append(f"비슷한 태그({', '.join(original_tags.intersection(candidate_tags))})를 공유해요.")
    
    sorted_candidates = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)

    similar_songs = []
    seen_song_ids = {identified_song_idx}
    seen_artist_ids = {identified_song['artist']}

    for idx, score in sorted_candidates:
        if idx in seen_song_ids or song_metadata[idx].get('artist') in seen_artist_ids:
            continue
        if len(similar_songs) >= 3:
            break
        
        song_info = song_metadata[idx]
        reasons_text = ", ".join(list(set(recommendation_reasons.get(idx, []))))

        similar_songs.append({
            "songId": song_info.get('spotify_id'),
            "songTitle": song_info['title'],
            "artist": song_info['artist'],
            "albumCoverUrl": song_info.get('album_cover_url'),
            "tagName": parse_tags(song_info.get('tags_normalized', '[]')),
            "songDescription": song_info.get('summary', 'N/A'),
            "matchLine": "", # No direct match line for text search recommendations
            "recommendationReason": reasons_text
        })
        seen_song_ids.add(idx)
        seen_artist_ids.add(song_info.get('artist'))

    return identified_song, matched_lyric, similar_songs


def search_pipeline_from_audio(query_text: str) -> (Dict[str, Any], str, List[Dict[str, Any]]):
    if line_index is None:
        return None, "", []

    query_vector = embedder.encode([query_text]).astype('float32')
    faiss.normalize_L2(query_vector)

    D, I = line_index.search(query_vector, 1)
    if not I.size: return None, "", []
    
    matched_line_idx = I[0][0]
    best_match_line_info = line_metadata[matched_line_idx]
    identified_song_idx = best_match_line_info['original_song_index']
    matched_lyric = best_match_line_info['line_text']

    raw_identified_song = song_metadata[identified_song_idx]
    identified_song = {
        "songId": raw_identified_song.get('spotify_id'),
        "songTitle": raw_identified_song.get('title'),
        "artist": raw_identified_song.get('artist'),
        "albumCoverUrl": raw_identified_song.get('album_cover_url'),
        "tagName": parse_tags(raw_identified_song.get('tags_normalized', '[]')),
        "songDescription": raw_identified_song.get('summary', 'N/A'),
        "userQuery": query_text
    }
    
    num_words = len(query_text.split())
    weight_song, weight_summary, weight_lyric = (0.5, 0.1, 0.4) if num_words > 5 else (0.6, 0.2, 0.2)

    identified_lyric_vector = line_embeddings[matched_line_idx:matched_line_idx+1]
    song_vector = song_embeddings[identified_song_idx:identified_song_idx+1]
    summary_vector = summary_embeddings[identified_song_idx:identified_song_idx+1]

    candidate_scores = defaultdict(float)
    recommendation_reasons = defaultdict(list)

    D_song, I_song = song_index.search(song_vector, 10)
    for i, idx in enumerate(I_song[0]):
        candidate_scores[idx] += D_song[0][i] * weight_song
        recommendation_reasons[idx].append("분위기와 장르가 비슷해요.")

    D_summary, I_summary = summary_index.search(summary_vector, 10)
    for i, idx in enumerate(I_summary[0]):
        candidate_scores[idx] += D_summary[0][i] * weight_summary
        recommendation_reasons[idx].append("곡의 전반적인 감성이 비슷해요.")

    D_lyric, I_lyric = line_index.search(identified_lyric_vector, 50)
    for i, line_idx in enumerate(I_lyric[0]):
        song_idx = line_metadata[line_idx]['original_song_index']
        if song_idx == identified_song_idx: continue
        candidate_scores[song_idx] += D_lyric[0][i] * weight_lyric
        recommendation_reasons[song_idx].append("가사가 비슷한 느낌을 줘요.")

    original_tags = set(identified_song['tagName'])
    for idx in list(candidate_scores.keys()):
        candidate_tags = set(parse_tags(song_metadata[idx].get('tags_normalized', '[]')))
        if original_tags.intersection(candidate_tags):
            candidate_scores[idx] += 0.1
            recommendation_reasons[idx].append(f"비슷한 태그({', '.join(original_tags.intersection(candidate_tags))})를 공유해요.")

    for i, idx in enumerate(I_song[0]): candidate_scores[idx] += (10 - i) * 0.005
    for i, idx in enumerate(I_summary[0]): candidate_scores[idx] += (10 - i) * 0.003
    for i, line_idx in enumerate(I_lyric[0]):
        song_idx = line_metadata[line_idx]['original_song_index']
        candidate_scores[song_idx] += (50 - i) * 0.001

    sorted_candidates = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)
    
    similar_songs = []
    seen_song_ids = {identified_song_idx}
    seen_artist_ids = {identified_song['artist']}

    for idx, score in sorted_candidates:
        if idx in seen_song_ids or song_metadata[idx].get('artist') in seen_artist_ids:
            continue
        
        if len(similar_songs) >= 3:
            break
        
        song_info = song_metadata[idx]
        recommended_lyric_snippet = "추천 근거 가사를 찾을 수 없습니다."
        
        candidate_line_indices = lines_by_song_idx.get(idx, [])
        if candidate_line_indices:
            candidate_vectors = line_embeddings[candidate_line_indices]
            similarities = np.dot(candidate_vectors, identified_lyric_vector.T).flatten()
            best_match_in_song_idx = similarities.argmax()
            original_line_idx = candidate_line_indices[best_match_in_song_idx]
            recommended_lyric_snippet = line_metadata[original_line_idx]['line_text']
        
        reasons_text = ", ".join(list(set(recommendation_reasons.get(idx, []))))

        similar_songs.append({
            "songId": song_info.get('spotify_id'),
            "songTitle": song_info['title'],
            "artist": song_info['artist'],
            "albumCoverUrl": song_info.get('album_cover_url'),
            "tagName": parse_tags(song_info.get('tags_normalized', '[]')),
            "songDescription": song_info.get('summary', 'N/A'),
            "matchLine": recommended_lyric_snippet,
            "recommendationReason": reasons_text
        })
        seen_song_ids.add(idx)
        seen_artist_ids.add(song_info.get('artist'))

    return identified_song, matched_lyric, similar_songs

@app.get("/")
def read_root(): return FileResponse('static/index.html')

@app.get("/login")
def login():
    auth_url = sp_oauth.get_authorize_url()
    return RedirectResponse(auth_url)

@app.get("/callback", response_class=HTMLResponse)
def callback(request: Request, code: str):
    token_info = sp_oauth.get_access_token(code, check_cache=False)
    encrypted_token_info = serializer.dumps(token_info)
    response = Response(content=f"""
    <script>
        if (window.opener) {{
            window.opener.postMessage({{ type: 'SPOTIFY_LOGIN_SUCCESS' }}, '*');
            window.close();
        }}
    </script>""", media_type="text/html")
    response.set_cookie(key=SESSION_COOKIE_NAME, value=encrypted_token_info, httponly=True, samesite="lax", secure=True)
    return response

@app.get("/access-token")
def get_access_token(request: Request, response: Response):
    encrypted_token_info = request.cookies.get(SESSION_COOKIE_NAME)
    if not encrypted_token_info: raise HTTPException(status_code=403, detail="Not logged in")
    try:
        token_info = serializer.loads(encrypted_token_info)
        if sp_oauth.is_token_expired(token_info):
            token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
            encrypted_token_info = serializer.dumps(token_info)
            response.set_cookie(key=SESSION_COOKIE_NAME, value=encrypted_token_info, httponly=True, samesite="lax", secure=True)
        return {"accessToken": token_info['access_token']}
    except Exception as e:
        logger.error(f"Failed to get access token: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve access token.")

@app.get("/me")
def get_me(request: Request):
    encrypted_token_info = request.cookies.get(SESSION_COOKIE_NAME)
    if not encrypted_token_info: return {"loggedIn": False}
    try:
        token_info = serializer.loads(encrypted_token_info)
        if sp_oauth.is_token_expired(token_info): raise Exception("Token expired")
        sp = spotipy.Spotify(auth=token_info['access_token'])
        user = sp.me()
        return {"loggedIn": True, "user": user}
    except Exception:
        return {"loggedIn": False}

@app.post("/stt")
async def speech_to_text_and_search(audio_file: UploadFile = File(...)):
    try:
        audio_bytes = await audio_file.read()
        audio = AudioSegment.from_file(io.BytesIO(audio_bytes))
        if (len(audio) / 1000.0) < 5.0:
            raise HTTPException(status_code=400, detail="오디오 파일은 최소 5초 이상이어야 합니다.")
        transcript = client.audio.transcriptions.create(model="whisper-1", file=(audio_file.filename, audio_bytes, audio_file.content_type))
        transcribed_text = transcript.text
        if not transcribed_text.strip():
            raise HTTPException(status_code=400, detail="음성을 인식하지 못했습니다.")
        
        identified_song, matched_lyric, similar_songs = search_pipeline_from_audio(transcribed_text)
        
        return {
            "song": identified_song,
            "lyrics": matched_lyric, 
            "recommendations": similar_songs
        }
    except Exception as e:
        logger.error(f"API 처리 중 에러 발생: {e}", exc_info=True)
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/text-search")
async def text_to_search(query_text: str = Form(...)):
    try:
        if not query_text.strip():
            raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")
        
        identified_song, matched_lyric, similar_songs = search_pipeline_from_text(query_text)

        return {
            "song": identified_song,
            "lyrics": matched_lyric,
            "recommendations": similar_songs
        }
    except Exception as e:
        logger.error(f"API 처리 중 에러 발생: {e}", exc_info=True)
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate-playlist-details")
async def generate_playlist_details(request_data: PlaylistDetailsRequest):
    try:
        songs_info = ""
        for i, song in enumerate(request_data.songs):
            songs_info += f"곡 {i+1}: {song.artist} - {song.songTitle}\n요약: {song.songDescription}\n태그: {', '.join(song.tagName)}\n\n"
        
        prompt = f"""
        다음 J-POP 곡들의 정보를 바탕으로, 이 곡들을 아우르는 창의적이고 매력적인 플레이리스트 제목(title)과 한 줄 설명(description)을 생성해줘.
        - 제목은 반드시 10단어 이내여야 해.
        - 설명은 반드시 25단어 이내여야 해.
        - 제목과 설명은 반드시 한국어로 작성해줘.
        - 감성적이고 흥미를 유발하는 문구를 사용해줘.
        - 최종 결과는 JSON 형식이어야 하고, 'title'과 'description' 키를 가져야 해.

        [곡 정보]
        {songs_info}
        """
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        logger.error(f"LLM failed: {e}", exc_info=True)
        return {"title": "AI 추천 J-POP", "description": "AI가 당신의 흥얼거림을 듣고 찾아낸 J-POP 추천곡 모음."}

@app.post("/create-playlist")
async def create_playlist(request: Request, playlist_data: PlaylistCreationRequest, response: Response):
    encrypted_token_info = request.cookies.get(SESSION_COOKIE_NAME)
    if not encrypted_token_info: raise HTTPException(status_code=403, detail="Not logged in")
    try:
        token_info = serializer.loads(encrypted_token_info)
        if sp_oauth.is_token_expired(token_info):
            token_info = sp_oauth.refresh_access_token(token_info['refresh_token'])
            encrypted_token_info = serializer.dumps(token_info)
            response.set_cookie(key=SESSION_COOKIE_NAME, value=encrypted_token_info, httponly=True, samesite="lax", secure=True)
        sp = spotipy.Spotify(auth=token_info['access_token'])
        song_ids = playlist_data.songIds
        if not song_ids: raise HTTPException(status_code=400, detail="No valid Spotify Track IDs found.")
        user_id = sp.me()['id']
        playlist = sp.user_playlist_create(
            user_id, 
            playlist_data.title, 
            public=True, 
            description=playlist_data.description
        )
        sp.playlist_add_items(playlist['id'], song_ids)
        return {"playlistId": playlist['id']}
    except Exception as e:
        logger.error(f"Playlist creation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create playlist.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

