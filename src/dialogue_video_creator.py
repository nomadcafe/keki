from moviepy.editor import (
    ImageClip,
    AudioFileClip,
    concatenate_audioclips,
    concatenate_videoclips,
    CompositeVideoClip,
)
from moviepy.audio.AudioClip import AudioClip, CompositeAudioClip
from moviepy.audio import fx as afx
import numpy as np
from pathlib import Path
from scipy.io import wavfile
from scipy import signal
import os
import tempfile


class DialogueVideoCreator:
    def __init__(self, bgm_path=None, bgm_volume: float = 0.15):
        """
        :param bgm_path: 背景BGMのファイルパス（未指定の場合は環境変数 VIDEO_BGM_PATH を使用）
        :param bgm_volume: BGM 音量（0.0〜1.0）
        """
        self.temp_files = []
        # BGM 設定（オプション）
        self.bgm_path = bgm_path or os.getenv("VIDEO_BGM_PATH") or ""
        self.bgm_volume = bgm_volume
    
    def create_silence(self, duration):
        """無音クリップを作成"""
        # サンプリングレート 24000 Hz (VOICEVOXと統一)
        sample_rate = 24000
        # 完全な無音（振幅0）の配列を作成
        silence_array = np.zeros((int(sample_rate * duration), 2))  # ステレオ
        
        # AudioArrayClipとして作成
        from moviepy.audio.AudioClip import AudioArrayClip
        return AudioArrayClip(silence_array, fps=sample_rate)
    
    def apply_highfreq_filter(self, audio_path):
        """音声ファイルに高周波フィルタを適用してビープ音を除去"""
        # フィルタ処理を無効化（audio_generator.pyで既に処理済み）
        return audio_path
    
    
    def cleanup_temp_files(self):
        """一時ファイルを削除"""
        for temp_file in self.temp_files:
            try:
                if os.path.exists(temp_file):
                    os.unlink(temp_file)
            except Exception as e:
                print(f"一時ファイル削除エラー: {e}")
        self.temp_files.clear()
    
    def create_dialogue_slide(self, image_path, audio_infos):
        """対話形式の音声を持つスライドから動画クリップを作成（改善版）"""
        # 画像クリップを作成
        image_clip = ImageClip(image_path)
        
        # H.264エンコーディングのため、幅と高さを偶数にする
        if image_clip.w % 2 != 0 or image_clip.h % 2 != 0:
            # PILのANTIALIAS互換性問題を回避するため、リサイズではなくクロップを使用
            new_width = image_clip.w if image_clip.w % 2 == 0 else image_clip.w - 1
            new_height = image_clip.h if image_clip.h % 2 == 0 else image_clip.h - 1
            image_clip = image_clip.crop(x1=0, y1=0, x2=new_width, y2=new_height)
        
        if audio_infos and any(info.get("audio_path") for info in audio_infos):
            audio_clips = []
            
            for i, info in enumerate(audio_infos):
                if info.get("audio_path") and Path(info["audio_path"]).exists():
                    # 音声ファイルに高周波フィルタを適用
                    filtered_audio_path = self.apply_highfreq_filter(info["audio_path"])
                    
                    # 音声クリップを読み込み（24kHzに統一）
                    audio_clip = AudioFileClip(filtered_audio_path, fps=24000)
                    
                    # 音声の開始と終了に改善されたフェードを適用（ビーン音防止）
                    fade_duration = 0.05  # 50ms（ビーン音除去の最適値）
                    if audio_clip.duration > fade_duration * 2:
                        from moviepy.audio.fx.audio_fadein import audio_fadein
                        from moviepy.audio.fx.audio_fadeout import audio_fadeout
                        audio_clip = audio_fadein(audio_clip, fade_duration)
                        audio_clip = audio_fadeout(audio_clip, fade_duration)
                    
                    # 音量を正規化（クリッピング防止）
                    audio_clip = audio_clip.volumex(0.95)
                    
                    # 音声をリストに追加
                    audio_clips.append(audio_clip)
                    
                    # 話者交代の間を追加（最後の音声以外）テンポアップ版
                    if i < len(audio_infos) - 1:
                        silence_duration = 0.2  # 200ms（テンポ向上・自然な会話リズム）
                        silence = self.create_silence(silence_duration)
                        audio_clips.append(silence)
            
            if audio_clips:
                # 音声クリップを改善された方法で連結（クロスフェード付き）
                if len(audio_clips) == 1:
                    combined_audio = audio_clips[0]
                else:
                    # 最初のクリップから始める
                    combined_audio = audio_clips[0]
                    
                    # 残りのクリップを順次結合（音声のみクロスフェード適用）
                    for i in range(1, len(audio_clips)):
                        current_clip = audio_clips[i]
                        
                        # 音声クリップ（無音ではない）の場合のみクロスフェード
                        if i % 2 == 1:  # 奇数インデックスは音声クリップ
                            # 短いクロスフェードで滑らかに接続
                            crossfade_duration = min(0.05, combined_audio.duration/10, current_clip.duration/10)
                            if crossfade_duration > 0.01:  # 10ms以上の場合のみ適用
                                from moviepy.audio.fx.audio_fadein import audio_fadein
                                current_clip = audio_fadein(current_clip, crossfade_duration)
                        
                        # クリップを結合
                        combined_audio = concatenate_audioclips([combined_audio, current_clip])
                
                # 全体の最後に短い余白を追加（テンポ重視版）
                final_silence_duration = 0.3  # 0.3秒（テンポ向上）
                final_silence = self.create_silence(final_silence_duration)
                combined_audio = concatenate_audioclips([combined_audio, final_silence])
                
                duration = combined_audio.duration
                image_clip = image_clip.set_duration(duration)
                image_clip = image_clip.set_audio(combined_audio)
            else:
                # 音声がない場合
                image_clip = image_clip.set_duration(5.0)
        else:
            # 音声情報がない場合
            image_clip = image_clip.set_duration(5.0)
        
        return image_clip
    
    def create_dialogue_video(self, image_paths, dialogue_audio_info, output_path="dialogue_output.mp4", fps=24):
        """対話形式の動画を作成"""
        clips = []
        
        # 各スライドのクリップを作成
        for i, image_path in enumerate(image_paths):
            # ファイル名からスライド番号を取得（例: slide_001.png -> 1）
            from pathlib import Path
            slide_num = int(Path(image_path).stem.split("_")[1])
            slide_key = f"slide_{slide_num}"
            audio_infos = dialogue_audio_info.get(slide_key, [])
            
            print(f"スライド {slide_num} ({slide_key}) の動画クリップを作成中... 音声: {len(audio_infos)} 個")
            clip = self.create_dialogue_slide(image_path, audio_infos)
            clips.append(clip)
        
        # すべてのクリップを連結（スライド間をクロスフェード）
        print(f"動画を連結中... 合計 {len(clips)} クリップ")
        print(f"dialogue_audio_info のキー: {list(dialogue_audio_info.keys())}")
        final_video = self._concatenate_with_crossfade(clips, crossfade_duration=0.4)
        print(f"最終動画の長さ: {final_video.duration} 秒")

        # オプション：背景BGMをミックス
        final_video = self._apply_background_music(final_video)
        
        # 動画全体の最後に長めのフェードアウトを追加（完全にブチっという音を防ぐ）
        fade_duration = 1.0  # 1.0秒のフェードアウトに延長
        if final_video.duration > fade_duration:
            # MoviePy 1.0.3では fx.fadeout を使用
            from moviepy.video.fx.fadeout import fadeout
            final_video = fadeout(final_video, fade_duration)
        
        # 動画を出力
        print(f"動画を出力中: {output_path}")
        # Docker環境での最適化（高画質版・QuickTime互換）
        # 一時音声ファイルのパスを生成
        temp_audiofile = tempfile.mktemp(suffix='.m4a')
        
        final_video.write_videofile(
            output_path,
            fps=fps,
            codec='libx264',
            audio_codec='aac',
            audio_fps=24000,  # 音声サンプリングレートを24kHzに統一
            preset='faster',  # 処理速度を優先しつつ品質も維持
            threads=16,  # スレッド数を増やして並列処理を強化
            bitrate='1500k',  # ビットレートを少し下げて処理速度改善
            audio_bitrate='192k',  # 音声品質は維持
            temp_audiofile=temp_audiofile,
            remove_temp=True,
            ffmpeg_params=[
                '-max_muxing_queue_size', '1024',  # メモリ不足対策
                '-pix_fmt', 'yuv420p',  # QuickTime互換のピクセルフォーマット
                '-movflags', '+faststart'  # Web再生に最適化（moov atomを先頭に配置）
            ]
        )
        
        # 一時ファイルのクリーンアップ
        self.cleanup_temp_files()
        
        print(f"動画出力完了: {output_path}")

    def _concatenate_with_crossfade(self, clips, crossfade_duration: float = 0.4):
        """
        スライド同士をクロスフェードでつなぐ
        - crossfade_duration: 各スライドの重なり時間（秒）
        """
        if not clips:
            raise ValueError("連結するクリップが存在しません")

        if len(clips) == 1:
            return clips[0]

        timeline_clips = []
        # 最初のクリップはそのまま配置
        prev_clip = clips[0]
        timeline_clips.append(prev_clip.set_start(0))
        current_time = prev_clip.duration

        for idx in range(1, len(clips)):
            clip = clips[idx]

            # クリップ長に応じて安全なクロスフェード時間を計算
            safe_cf = min(
                crossfade_duration,
                max(0.0, prev_clip.duration / 2.0),
                max(0.0, clip.duration / 2.0),
            )

            if safe_cf <= 0:
                # クロスフェードできない場合は通常の連結
                placed = clip.set_start(current_time)
                current_time += clip.duration
            else:
                # 直前のクリップの終わり safe_cf 秒前からフェードインしながら重ねる
                start_time = max(0.0, current_time - safe_cf)
                try:
                    placed = clip.set_start(start_time).crossfadein(safe_cf)
                except AttributeError:
                    # crossfadein メソッドが無い場合のフォールバック（フェードなしでオーバーラップ）
                    placed = clip.set_start(start_time)

                current_time = start_time + clip.duration

            timeline_clips.append(placed)
            prev_clip = clip

        final = CompositeVideoClip(timeline_clips)
        final.duration = current_time
        return final

    def _apply_background_music(self, video_clip):
        """
        背景BGMを動画にミックス（BGMパスが設定されている場合のみ）
        - VIDEO_BGM_PATH またはコンストラクタ引数でパスを指定
        - 自動的に動画の長さまでループし、音量とフェードイン/アウトを適用
        """
        if not self.bgm_path:
            # BGM 未設定の場合はそのまま返す
            return video_clip

        bgm_file = Path(self.bgm_path)
        if not bgm_file.exists():
            print(f"BGMファイルが見つかりません: {bgm_file}")
            return video_clip

        bgm_audio = None
        try:
            bgm_audio = AudioFileClip(str(bgm_file))

            # 動画の長さに合わせてループし、音量を調整
            bgm = bgm_audio.fx(afx.audio_loop, duration=video_clip.duration).volumex(
                self.bgm_volume
            )

            # BGM 自体にもフェードイン/アウトを適用して違和感を低減
            from moviepy.audio.fx.audio_fadein import audio_fadein
            from moviepy.audio.fx.audio_fadeout import audio_fadeout

            fade_dur = min(2.0, video_clip.duration / 4)
            if fade_dur > 0:
                bgm = audio_fadein(bgm, fade_dur)
                bgm = audio_fadeout(bgm, fade_dur)

            # 既存のナレーション音声とミックス
            if video_clip.audio is not None:
                mixed_audio = CompositeAudioClip([video_clip.audio, bgm])
            else:
                mixed_audio = bgm

            return video_clip.set_audio(mixed_audio)

        except Exception as e:
            print(f"BGMミックス中にエラー: {e}")
            return video_clip

        finally:
            try:
                if bgm_audio is not None:
                    bgm_audio.close()
            except Exception:
                pass