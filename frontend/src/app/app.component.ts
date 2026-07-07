import { Component, OnInit, NgZone, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';

declare var Spotify: any;

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent implements OnInit {
  title = 'frontend';
  view: 'initial' | 'results' = 'initial';
  isRecording = false;
  statusHtml = '';
  showTextModal = false;
  textInput = '';
  
  identifiedSong: any = null;
  matchedLyric = '';
  recommendations: any[] = [];
  songData: any[] = [];
  
  tagColorMap: any = {};
  failureHtml = '';
  
  // Player state
  showPlayer = false;
  isPlayerReady = false;
  deviceId: string | null = null;
  spotifyPlayer: any = null;
  playerTitle = '';
  playerDesc = '';
  playerPaused = true;
  playerProgress = 0;
  isPlaylistView = false;
  playerCovers: string[] = [];
  playerSingleCover = '';
  currentPlayingId = '';
  
  currentPlaylistId: string | null = null;
  isCreatingPlaylist = false;
  
  toasts: {message: string, isSuccess: boolean}[] = [];
  
  mediaRecorder: any;
  audioChunks: any[] = [];
  recordingTimer: any;
  recordingStartTime = 0;

  private API_URL = 'http://localhost:7860'; // Backend URL

  constructor(private http: HttpClient, private ngZone: NgZone) {}

  ngOnInit() {
    this.http.get('/assets/tag_colors.json').subscribe({
      next: (data) => this.tagColorMap = data,
      error: (e) => console.error('Failed to load tag_colors.json', e)
    });
    
    (window as any).onSpotifyWebPlaybackSDKReady = () => {
      console.log("Spotify SDK is ready.");
    };
  }

  @HostListener('window:message', ['$event'])
  async onMessage(event: MessageEvent) {
    if (event.data.type === 'SPOTIFY_LOGIN_SUCCESS') {
      try {
        const res: any = await this.http.get(`${this.API_URL}/access-token`, { withCredentials: true }).toPromise();
        if (res?.accessToken) {
          sessionStorage.setItem('spotify-access-token', res.accessToken);
          this.showToast('Spotify 로그인 완료!');
          if (this.currentPlaylistId) {
             this.playDirectly();
          } else {
             this.createPlaylist();
          }
        }
      } catch (e: any) {
        this.showToast(`로그인 오류: ${e.message}`, false);
      }
    }
  }

  showToast(message: string, isSuccess = true) {
    const toast = { message, isSuccess };
    this.toasts.push(toast);
    setTimeout(() => {
      this.toasts = this.toasts.filter(t => t !== toast);
    }, 3000);
  }

  showInitialView() {
    this.view = 'initial';
    this.statusHtml = '';
    this.identifiedSong = null;
    this.recommendations = [];
    this.songData = [];
    this.showPlayer = false;
  }

  toggleRecording() {
    if (this.mediaRecorder && this.mediaRecorder.state === 'recording') {
      clearTimeout(this.recordingTimer);
      this.mediaRecorder.stop();
    } else {
      this.startRecording();
    }
  }

  async startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      this.mediaRecorder = new (window as any).MediaRecorder(stream);
      this.audioChunks = [];
      
      this.mediaRecorder.ondataavailable = (event: any) => this.audioChunks.push(event.data);
      this.mediaRecorder.onstop = async () => {
        this.isRecording = false;
        if ((Date.now() - this.recordingStartTime) < 5000) {
          this.statusHtml = '오류: 최소 5초 이상 녹음해주세요.';
          return;
        }
        
        this.statusHtml = '음성 처리 중... <div class="inline-block ml-2 w-4 h-4 border-2 border-t-transparent border-violet-500 rounded-full animate-spin"></div>';
        const audioBlob = new Blob(this.audioChunks, { type: 'audio/webm' });
        await this.sendDataToServer(audioBlob, 'audio');
        stream.getTracks().forEach(track => track.stop());
      };

      this.mediaRecorder.start();
      this.recordingStartTime = Date.now();
      this.isRecording = true;
      this.statusHtml = '노래를 흥얼거려주세요... (최대 15초)';
      
      this.recordingTimer = setTimeout(() => {
        if (this.mediaRecorder.state === 'recording') this.mediaRecorder.stop();
      }, 15000);
    } catch(err) {
      this.statusHtml = '마이크 접근 권한이 필요합니다.';
    }
  }

  openTextModal() {
    this.showTextModal = true;
  }

  closeTextModal(event?: Event) {
    this.showTextModal = false;
  }

  async submitText() {
    const text = this.textInput.trim();
    if (!text) {
      this.showToast('오류: 검색어를 입력해주세요.', false);
      return;
    }
    this.showTextModal = false;
    this.textInput = '';
    
    this.statusHtml = '텍스트 처리 중... <div class="inline-block ml-2 w-4 h-4 border-2 border-t-transparent border-violet-500 rounded-full animate-spin"></div>';
    await this.sendDataToServer(text, 'text');
  }

  async sendDataToServer(data: any, type: 'audio' | 'text') {
    try {
      const formData = new FormData();
      let endpoint = '';
      if (type === 'audio') {
        formData.append('audio_file', data, 'recording.webm');
        endpoint = '/stt';
      } else {
        formData.append('query_text', data);
        endpoint = '/text-search';
      }
      
      const response: any = await this.http.post(`${this.API_URL}${endpoint}`, formData).toPromise();
      this.displayResults(response);
    } catch (error: any) {
      this.statusHtml = '';
      this.showToast(`오류: ${error.message || '서버 오류'}`, false);
      this.showInitialView();
    }
  }

  displayResults(data: any) {
    this.view = 'results';
    this.statusHtml = '';
    
    if (!data.song) {
      this.failureHtml = `<p class="p-4 bg-gray-100 rounded-lg">아쉽지만 일치하는 곡을 찾지 못했어요. 😥 다른 검색어로 다시 시도해 보세요!</p>`;
      return;
    }

    this.identifiedSong = data.song;
    this.matchedLyric = data.lyrics;
    this.recommendations = data.recommendations || [];
    this.songData = [this.identifiedSong, ...this.recommendations];
    this.currentPlaylistId = null;
  }

  async playDirectly() {
     this.handlePlay(true);
  }

  async playCreatedPlaylist() {
     this.handlePlay(false);
  }

  async handlePlay(isDirectPlay: boolean) {
     try {
       const meResponse: any = await this.http.get(`${this.API_URL}/me`, { withCredentials: true }).toPromise();
       if (!meResponse.loggedIn) {
         window.open(`${this.API_URL}/login`, 'SpotifyLogin', 'width=500,height=600');
         return;
       }

       const token = sessionStorage.getItem('spotify-access-token');
       if (!token) {
         window.open(`${this.API_URL}/login`, 'SpotifyLogin', 'width=500,height=600');
         return;
       }
       
       await this.initializePlayer(token);
       
       if (!this.isPlayerReady || !this.deviceId) {
         this.showToast('플레이어 기기를 찾을 수 없습니다. Spotify 앱이 활성화되어 있는지 확인 후 다시 시도해주세요.', false);
         return;
       }

       if(isDirectPlay){
         const trackUris = this.songData
            .map(s => s.songId ? `spotify:track:${s.songId}` : null)
            .filter(uri => uri !== null) as string[];
         if (trackUris.length > 0) {
            this.renderModernPlayerUI();
            await this.playTracks(trackUris, token);
         } else {
            this.showToast('재생할 수 있는 Spotify 트랙이 없습니다.', false);
         }
       } else {
         this.renderModernPlayerUI({ title: this.playerTitle, description: this.playerDesc });
         await this.playPlaylist(`spotify:playlist:${this.currentPlaylistId}`, token);
       }
     } catch (initError: any) {
       this.showToast(`플레이어 오류: ${initError.message}`, false);
       if (initError.message.toLowerCase().includes('authentication')) {
         sessionStorage.removeItem('spotify-access-token');
         window.open(`${this.API_URL}/login`, 'SpotifyLogin', 'width=500,height=600');
       }
     }
  }

  async initializePlayer(token: string): Promise<any> {
    if (this.spotifyPlayer) {
      this.spotifyPlayer.disconnect();
      this.spotifyPlayer = null;
      this.isPlayerReady = false;
      this.deviceId = null;
    }

    return new Promise((resolve, reject) => {
      this.spotifyPlayer = new Spotify.Player({
        name: 'UR-FIT J-POP Player',
        getOAuthToken: (cb: any) => { cb(token); },
        volume: 0.5
      });

      this.spotifyPlayer.addListener('ready', ({ device_id }: any) => {
        this.ngZone.run(() => {
            this.deviceId = device_id;
            this.isPlayerReady = true;
            resolve(this.spotifyPlayer);
        });
      });
      
      this.spotifyPlayer.addListener('player_state_changed', (state: any) => {
        if (!state) return;
        this.ngZone.run(() => this.updatePlayerUI(state));
      });

      this.spotifyPlayer.addListener('authentication_error', ({ message }: any) => {
        sessionStorage.removeItem('spotify-access-token');
        this.isPlayerReady = false;
        this.deviceId = null;
        reject(new Error(message));
      });
      
      ['initialization_error', 'account_error', 'playback_error'].forEach(errorType => {
        this.spotifyPlayer.addListener(errorType, ({ message }: any) => {
          reject(new Error(message));
        });
      });

      this.spotifyPlayer.connect();
    });
  }

  renderModernPlayerUI(playlistInfo: any = null) {
     this.showPlayer = true;
     this.playerTitle = playlistInfo ? playlistInfo.title : "AI 추천 J-POP";
     this.playerDesc = playlistInfo ? playlistInfo.description : "선택한 곡들을 재생합니다.";
     this.isPlaylistView = !!playlistInfo;
     
     if (this.isPlaylistView && this.songData.length > 0) {
         let covers = this.songData.map(s => s.albumCoverUrl || 'https://placehold.co/100x100').slice(0, 4);
         while(covers.length > 0 && covers.length < 4) covers.push(...covers.slice(0, 4 - covers.length));
         this.playerCovers = covers;
     } else if (this.songData.length > 0) {
         this.playerSingleCover = this.songData[0].albumCoverUrl || 'https://placehold.co/100x100';
     }
  }

  updatePlayerUI(state: any) {
    this.playerPaused = state.paused;
    this.playerProgress = (state.position / state.duration) * 100;

    if (state.track_window.current_track) {
      const currentTrack = state.track_window.current_track;
      if (!this.isPlaylistView) {
        this.playerSingleCover = currentTrack.album.images[0].url;
      }
      this.playerTitle = currentTrack.name;
      this.playerDesc = currentTrack.artists.map((a: any) => a.name).join(', ');
      this.currentPlayingId = currentTrack.id;
    }
  }

  togglePlay() { this.spotifyPlayer?.togglePlay(); }
  nextTrack() { this.spotifyPlayer?.nextTrack(); }
  prevTrack() { this.spotifyPlayer?.previousTrack(); }
  
  seekPlayer(event: MouseEvent) {
    const barWidth = (event.currentTarget as HTMLElement).offsetWidth;
    const clickX = event.offsetX;
    this.spotifyPlayer?.getCurrentState().then((state: any) => {
        if (state) {
            const newPosition = (clickX / barWidth) * state.duration;
            this.spotifyPlayer.seek(newPosition);
        }
    });
  }

  async playTracks(trackUris: string[], token: string) {
    try {
        await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${this.deviceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ uris: trackUris })
        });
    } catch (error: any) {
        this.showToast(`재생 실패: ${error.message}`, false);
    }
  }

  async playPlaylist(playlistUri: string, token: string) {
    try {
        await fetch(`https://api.spotify.com/v1/me/player/play?device_id=${this.deviceId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
            body: JSON.stringify({ context_uri: playlistUri })
        });
    } catch (error: any) {
        this.showToast(`재생 실패: ${error.message}`, false);
    }
  }

  async createPlaylist() {
    this.isCreatingPlaylist = true;
    try {
      const meResponse: any = await this.http.get(`${this.API_URL}/me`, { withCredentials: true }).toPromise();
      if (!meResponse.loggedIn) {
        window.open(`${this.API_URL}/login`, 'SpotifyLogin', 'width=500,height=600');
        this.isCreatingPlaylist = false;
        return;
      }

      const songsForLLM = this.songData.map(s => ({
        artist: s.artist, songTitle: s.songTitle, songDescription: s.songDescription, tagName: s.tagName || []
      }));
      
      const playlistDetails: any = await this.http.post(`${this.API_URL}/generate-playlist-details`, { songs: songsForLLM }).toPromise();
      await this.createPlaylistOnSpotify(playlistDetails.title, playlistDetails.description);
    } catch (e: any) {
      this.showToast(`오류: ${e.message}. 기본 보로 생성합니다.`, false);
      await this.createPlaylistOnSpotify("AI 추천 J-POP", "AI가 당신의 흥얼거림을 듣고 찾아낸 J-POP 추천곡 모음.");
    }
  }

  async createPlaylistOnSpotify(title: string, description: string) {
    this.playerTitle = title;
    this.playerDesc = description;

    try {
      const songIds = this.songData.map(s => s.songId).filter(id => id);
      const playlistData: any = await this.http.post(`${this.API_URL}/create-playlist`, { songIds: songIds, title, description }, { withCredentials: true }).toPromise();
      
      this.currentPlaylistId = playlistData.playlistId;
      this.showToast(`플레이리스트 "${title}" 생성 완료!`);
      this.isCreatingPlaylist = false;
    } catch (e: any) {
      this.showToast(`생성 실패: ${e.message}`, false);
      this.isCreatingPlaylist = false;
    }
  }
}
