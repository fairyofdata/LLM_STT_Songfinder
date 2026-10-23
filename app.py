import os
import uvicorn
import json
import openai
from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Depends, Response, Form
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from logging import getLogger, basicConfig, INFO
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from itsdangerous import URLSafeSerializer
from pydantic import BaseModel, Field, AliasChoices
from typing import List, Dict, Any
from pydub import AudioSegment
import io

from search import SongIndex

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
try:
    index = SongIndex.load(os.getenv("SONGFINDER_DATA_DIR", "."))
    logger.info(f"DB 로드 완료. {len(index.song_metadata)}곡, {len(index.line_metadata)}개의 라인, "
                f"{len(index.summary_embeddings)}개의 요약문이 준비되었습니다.")
except Exception as e:
    logger.error(f"DB 로딩 실패: {e}", exc_info=True)
    index = None

# Whisper often hears Japanese lyrics read with a Korean accent as Korean and writes Hangul,
# which the Japanese lyric index cannot match; retry those as Japanese (see docs/EVALUATION.md).
KO_TO_JA_FALLBACK = os.getenv("SONGFINDER_KO_TO_JA_FALLBACK", "1") == "1"

REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:7860/callback")
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIPY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
    redirect_uri=REDIRECT_URI,
    scope="streaming user-read-private user-read-email user-read-playback-state user-modify-playback-state user-read-currently-playing playlist-modify-public playlist-modify-private")

api_key = os.getenv("OPENAI_API_KEY") or os.getenv("openai")  # README documents OPENAI_API_KEY
client = openai.OpenAI(api_key=api_key) if api_key else None

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://localhost:5173", "http://127.0.0.1:4200", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def search_pipeline_from_text(query_text: str) -> (Dict[str, Any], str, List[Dict[str, Any]]):
    if index is None:
        return None, "", []
    hit = index.identify_text(query_text)
    if hit is None:
        return None, "", []
    song_idx = hit['song']
    if hit['via'] == 'summary':
        matched_lyric = index.song_metadata[song_idx].get('summary', 'N/A')
    else:
        matched_lyric = index.line_metadata[hit['line']]['line_text']
    return index.song_card(song_idx, query_text), matched_lyric, index.recommend_for_text(song_idx)


def search_pipeline_from_audio(query_text: str) -> (Dict[str, Any], str, List[Dict[str, Any]]):
    if index is None:
        return None, "", []
    hit = index.identify_transcript(query_text)
    song_idx, line_idx = hit['song'], hit['line']
    return (index.song_card(song_idx, query_text), index.line_metadata[line_idx]['line_text'],
            index.recommend_for_audio(song_idx, line_idx, query_text))


def transcribe(filename: str, audio_bytes: bytes, content_type: str) -> str:
    def run(**kwargs):
        return client.audio.transcriptions.create(model="whisper-1", file=(filename, audio_bytes, content_type),
                                                  response_format="verbose_json", **kwargs)
    transcript = run()
    language = (getattr(transcript, "language", "") or "").lower()
    if KO_TO_JA_FALLBACK and language in ("korean", "ko"):
        logger.info("Whisper detected Korean; transcribing again as Japanese.")
        transcript = run(language="ja")
    return transcript.text

@app.get("/")
def read_root(): return {"message": "API is running."}

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
        transcribed_text = transcribe(audio_file.filename, audio_bytes, audio_file.content_type)
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

