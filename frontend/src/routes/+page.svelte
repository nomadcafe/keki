<script lang="ts">
  import { onMount, onDestroy, tick } from "svelte";
  import { goto } from "$app/navigation";
  import { page } from "$app/stores";
  import { authenticatedFetch, getApiKey, getDefaultProvider } from "$lib/auth.ts";
  import { t } from "$lib/i18n/index.js";
  import TimelineEditor from "$lib/TimelineEditor.svelte";
  // getApiUrl は削除されました - 直接URLパスを使用

  interface Job {
    job_id: string;
    status: string;
    status_code?: string;
    progress: number;
    result_url?: string;
    error_code?: string;
  }

  interface DialogueData {
    [key: string]: Array<{
      speaker: string;
      text: string;
    }>;
  }

  interface Slide {
    slide_number: number;
    url: string;
  }

  interface DialogueResponse {
    dialogue_data: DialogueData;
    estimated_duration: {
      seconds: number;
      formatted: string;
    };
  }

  let selectedFile: File | null = null;
  let currentJob: Job | null = null;
  let isUploading = false;
  let dragover = false;
  let dialogueData: DialogueData | null = null;
  let estimatedDuration: { seconds: number; formatted: string } | null = null;
  let editingDialogue = false;
  let additionalPrompt = "";
  let currentStep: "upload" | "dialogue" | "video" = "upload";
  let viewMode: "list" | "timeline" = "list"; // 表示モード: リスト or タイムライン
  let slides: Slide[] = [];
  let isRegenerating = false;
  let instructionHistory: any = {};
  let showHistory = false;
  let showHistoryForSlide: string | null = null;
  let targetDuration = 10; // デフォルト10分
  let availableSpeakers: any[] = [];
  let selectedSpeaker1Id = 2;
  let selectedSpeaker2Id = 3;
  let speaker1Speed = 1.0;
  let speaker2Speed = 1.0;
  let speakersLoading = false;
  let showRecommendations = false;
  let playingSampleId: number | null = null;
  let currentJobMetadata: any = null; // 現在のジョブのメタデータ
  let modalImageUrl: string | null = null; // モーダル表示用の画像URL
  let isUpdatingDialogue = false; // 対話データ更新中フラグ
  let selectedConversationStyle = "friendly"; // 選択された会話スタイル
  let showApiKeyWarning = false; // APIキー未設定警告の表示
  let hasAnyApiKey = false; // いずれかのAPIキーが設定されているか
  let isAuthenticated = false; // 認証状態
  let authEnabled = false; // 認証が有効かどうか
  let knowledgeExpanded = false; // ナレッジ入力欄の展開状態
  let knowledgeFile: File | null = null; // ナレッジファイル
  let showIntro = false; // 紹介セクションの表示状態（landing pageがあるため非表示）
  let slideImportance: Record<number, number> = {}; // スライド重要度マップ（スライド番号 -> 重要度 0.5-1.5）
  let isSavingImportance = false; // 重要度保存中フラグ
  // BGMと転場設定
  let bgmEnabled = false; // BGM有効化
  let bgmPath = ""; // BGMファイルパス
  let bgmVolume = 0.15; // BGM音量（0.0-1.0）
  let transitionType = "crossfade"; // 転場タイプ
  let transitionDuration = 0.4; // 転場時間（秒）
  let showVideoSettings = false; // 動画設定パネルの表示状態
  // リアルタイムプレビュー（スライドフォーカス・音声プレビュー）
  let previewSlideKey: string | null = null; // フォーカス中スライドのキー（slide_N）
  let voicePreviewKey: string | null = null; // 「slideKey_index」ローディング表示用
  let previewAudioEl: HTMLAudioElement | null = null; // プレビュー再生用（前回URL解放）

  // ステータス表示用のヘルパー関数
  function getDisplayStatus(job: Job): string {
    return t(`status.${job.status_code || job.status}`);
  }

  function getDisplayMessage(job: Job): string {
    return t(`status.${job.status_code}`);
  }

  function getDisplayError(job: Job): string {
    return job.error_code ? t(`errors.${job.error_code}`) : "";
  }

  /** 対話の speaker 値から VOICEVOX 用の style_id / 名前 / 速度を取得 */
  function getVoiceParamsForDialogueSpeaker(speaker: string): {
    id: number;
    name: string;
    speed: number;
  } | null {
    if (!currentJobMetadata) return null;
    if (speaker === "speaker1" || speaker === "metan") {
      return {
        id: currentJobMetadata.speaker1?.id ?? selectedSpeaker1Id ?? 2,
        name: currentJobMetadata.speaker1?.name ?? "四国めたん",
        speed:
          currentJobMetadata.speaker1?.speed != null
            ? currentJobMetadata.speaker1.speed
            : speaker1Speed,
      };
    }
    if (speaker === "speaker2" || speaker === "zundamon") {
      return {
        id: currentJobMetadata.speaker2?.id ?? selectedSpeaker2Id ?? 3,
        name: currentJobMetadata.speaker2?.name ?? "ずんだもん",
        speed:
          currentJobMetadata.speaker2?.speed != null
            ? currentJobMetadata.speaker2.speed
            : speaker2Speed,
      };
    }
    return {
      id: selectedSpeaker2Id ?? 3,
      name: String(speaker),
      speed: speaker2Speed,
    };
  }

  /** 全文音声合成前に、当該セリフのみ VOICEVOX で試聴 */
  async function previewDialogueLine(
    slideKey: string,
    index: number,
    text: string,
    speaker: string
  ) {
    const key = `${slideKey}_${index}`;
    const trimmed = text.trim();
    if (!trimmed) {
      alert("テキストを入力してください");
      return;
    }
    const params = getVoiceParamsForDialogueSpeaker(speaker);
    if (!params) {
      alert("話者情報を読み込めません。しばらく待ってから再度お試しください。");
      return;
    }
    const previewText =
      trimmed.length > 400 ? trimmed.slice(0, 400) + "…" : trimmed;
    voicePreviewKey = key;
    try {
      const response = await fetch("/api/voice-sample", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          speaker_id: params.id,
          speaker_name: params.name,
          speed: params.speed,
          text: previewText,
        }),
      });
      if (!response.ok) {
        const err = await response.text();
        throw new Error(err || "音声プレビューに失敗しました");
      }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      if (previewAudioEl) {
        previewAudioEl.pause();
        if (previewAudioEl.src.startsWith("blob:")) {
          URL.revokeObjectURL(previewAudioEl.src);
        }
      }
      previewAudioEl = new Audio(url);
      previewAudioEl.play();
      previewAudioEl.addEventListener("ended", () => {
        URL.revokeObjectURL(url);
      });
    } catch (e) {
      console.error(e);
      alert("音声プレビューに失敗しました。VOICEVOX が起動しているか確認してください。");
    } finally {
      voicePreviewKey = null;
    }
  }

  function setFirstSlideAsPreview() {
    if (!dialogueData) return;
    const keys = Object.keys(dialogueData).sort(
      (a, b) => parseInt(a.split("_")[1]) - parseInt(b.split("_")[1])
    );
    previewSlideKey = keys[0] ?? null;
  }

  // 会話スタイルの定義
  const conversationStyles = [
    {
      id: "radio",
      name: "🎤 ラジオ風",
      description: "リスナーに語りかけるような親しみやすいスタイル",
      prompt:
        "ラジオ番組のようにリスナーに語りかけるスタイルで。「リスナーのみなさん」「いかがでしょうか」などの表現を使い、暖かく親しみやすい雰囲気で。",
    },
    {
      id: "business",
      name: "💼 ビジネスライク",
      description: "プロフェッショナルで信頼感のあるスタイル",
      prompt:
        "ビジネスシーンに適したプロフェッショナルなスタイルで。敬語を適切に使い、論理的で説得力のある説明を心がけて。",
    },
    {
      id: "friendly",
      name: "😊 友達風",
      description: "カジュアルでフレンドリーなスタイル",
      prompt:
        "友達同士が話しているようなカジュアルなスタイルで。「だよね～」「っていうか」など、日常会話のような表現で。",
    },
    {
      id: "educational",
      name: "🎓 教育番組風",
      description: "子供向け教育番組のようなスタイル",
      prompt:
        "教育番組のようにわかりやすく、楽しく学べるスタイルで。「みんなも一緒に考えてみよう！」「すごい発見だね！」など、前向きな表現で。",
    },
    {
      id: "news",
      name: "📰 ニュース番組風",
      description: "キャスターが伝えるようなスタイル",
      prompt:
        "ニュース番組のように事実を正確に伝えるスタイルで。「さて、続いては」「詳しく見ていきましょう」など、フォーマルな表現で。",
    },
    {
      id: "podcast",
      name: "🎧 ポッドキャスト風",
      description: "ディープな話題を探求するスタイル",
      prompt:
        "ポッドキャストのように深い話題を探求するスタイルで。「これは興味深い点ですね」「もう少し掘り下げてみると」など、思考を深める表現で。",
    },
    {
      id: "variety",
      name: "🎨 バラエティ番組風",
      description: "明るく楽しいエンターテイメント風",
      prompt:
        "バラエティ番組のように明るく楽しいスタイルで。ツッコミやボケ、驚きのリアクションなどを取り入れて。「えー！」「マジで！？」など。",
    },
    {
      id: "commentary",
      name: "🎮 実況解説風",
      description: "スポーツ実況のような臨場感あるスタイル",
      prompt:
        "スポーツ実況のように臨場感あふれるスタイルで。「おっと、これは！」「素晴らしい展開です！」など、テンポよく盛り上げて。",
    },
  ];

  // ビジネス向けおすすめ組み合わせ
  const businessRecommendations = [
    {
      name: "最もプロフェッショナル",
      description: "企業向けプレゼンや研修動画に最適",
      speaker1: { id: 13, name: "青山龍星" },
      speaker2: { id: 16, name: "九州そら" },
    },
    {
      name: "バランス型",
      description: "幅広いビジネスシーンに対応",
      speaker1: { id: 11, name: "玄野武宏" },
      speaker2: { id: 8, name: "春日部つむぎ" },
    },
    {
      name: "若手向け",
      description: "スタートアップや若手向けコンテンツに",
      speaker1: { id: 14, name: "冥鳴ひまり" },
      speaker2: { id: 12, name: "白上虎太郎" },
    },
  ];

  async function loadSpeakers() {
    speakersLoading = true;
    try {
      const response = await authenticatedFetch("/api/speakers");
      if (response.ok) {
        availableSpeakers = await response.json();
      }
    } catch (error) {
      console.error("スピーカー一覧の取得に失敗:", error);
    } finally {
      speakersLoading = false;
    }
  }

  onMount(async () => {
    // 認証チェックを最初に実行
    await checkAuthStatus();

    loadSpeakers();
    // APIキーの設定状態をチェック
    await checkApiKeyStatus();

    // 履歴から「再編集」で遷移した場合: URL の job_id でジョブを読み込む
    const jobIdFromUrl = $page.url.searchParams.get("job_id");
    if (jobIdFromUrl) {
      try {
        const res = await fetch(`/api/jobs/${jobIdFromUrl}/status`);
        if (res.ok) {
          const status = await res.json();
          currentJob = {
            job_id: status.job_id,
            status: status.status,
            status_code: status.status_code,
            progress: status.progress ?? 0,
            result_url: status.result_url,
            error_code: status.error_code,
          };
          await loadDialogue(jobIdFromUrl, true);
        }
      } catch (e) {
        console.error("履歴ジョブの読み込みに失敗しました:", e);
      }
    }
  });

  onDestroy(() => {
    if (previewAudioEl) {
      previewAudioEl.pause();
      if (previewAudioEl.src.startsWith("blob:")) {
        URL.revokeObjectURL(previewAudioEl.src);
      }
      previewAudioEl = null;
    }
  });

  async function checkAuthStatus() {
    try {
      const response = await authenticatedFetch("/api/auth/status");
      if (response.ok) {
        const data = await response.json();
        authEnabled = data.auth_enabled;
        isAuthenticated = data.authenticated;

        // 認証が有効で未認証の場合はログインページにリダイレクト
        if (authEnabled && !isAuthenticated) {
          goto("/login");
          return;
        }
      }
    } catch (error) {
      console.error("認証状態の確認に失敗:", error);
    }
  }

  async function checkApiKeyStatus() {
    try {
      const response = await fetch("/api/settings/providers");
      if (response.ok) {
        const data = await response.json();
        // いずれかのプロバイダーが設定されているかチェック
        hasAnyApiKey = data.providers.some((p: any) => p.configured);

        // APIキーが1つも設定されていない場合は警告を表示
        if (!hasAnyApiKey) {
          showApiKeyWarning = true;
        }
      }
    } catch (error) {
      console.error("APIキー状態の確認に失敗:", error);
    }
  }

  // スピーカーが変更されたときに速度を自動調整
  $: if (availableSpeakers.length > 0 && selectedSpeaker1Id) {
    const speaker1 = availableSpeakers.find(
      (s) => s.style_id === selectedSpeaker1Id
    );
    if (speaker1 && speaker1.speaker_name === "九州そら") {
      speaker1Speed = 1.5;
    } else if (
      speaker1 &&
      speaker1.speaker_name !== "九州そら" &&
      speaker1Speed === 1.5
    ) {
      // 九州そら以外が選択された場合は1.0に戻す
      speaker1Speed = 1.0;
    }
  }

  $: if (availableSpeakers.length > 0 && selectedSpeaker2Id) {
    const speaker2 = availableSpeakers.find(
      (s) => s.style_id === selectedSpeaker2Id
    );
    if (speaker2 && speaker2.speaker_name === "九州そら") {
      speaker2Speed = 1.5;
    } else if (
      speaker2 &&
      speaker2.speaker_name !== "九州そら" &&
      speaker2Speed === 1.5
    ) {
      // 九州そら以外が選択された場合は1.0に戻す
      speaker2Speed = 1.0;
    }
  }

  function applyRecommendation(recommendation: any) {
    selectedSpeaker1Id = recommendation.speaker1.id;
    selectedSpeaker2Id = recommendation.speaker2.id;
    showRecommendations = false;
  }

  async function playVoiceSample(
    speakerId: number,
    speakerName: string,
    speed: number
  ) {
    try {
      playingSampleId = speakerId;

      const sampleText =
        speakerName === "ずんだもん"
          ? "こんにちは！ずんだもんなのだ！"
          : `こんにちは！${speakerName}です。よろしくお願いします。`;

      const response = await fetch("/api/voice-sample", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          speaker_id: speakerId,
          speaker_name: speakerName,
          speed: speed,
          text: sampleText,
        }),
      });

      if (response.ok) {
        const blob = await response.blob();
        const audioUrl = URL.createObjectURL(blob);
        const audio = new Audio(audioUrl);

        await audio.play();

        // メモリリークを防ぐためにURLを解放
        audio.addEventListener("ended", () => {
          URL.revokeObjectURL(audioUrl);
          playingSampleId = null;
        });
      } else {
        playingSampleId = null;
      }
    } catch (error) {
      console.error("サンプルボイスの再生に失敗:", error);
      playingSampleId = null;
    }
  }

  async function handleFileSelect(event: Event) {
    const target = event.target as HTMLInputElement;
    if (target.files && target.files[0]) {
      selectedFile = target.files[0];
    }
  }

  async function handleKnowledgeFileSelect(event: Event) {
    const target = event.target as HTMLInputElement;
    if (target.files && target.files[0]) {
      knowledgeFile = target.files[0];
    }
  }

  async function handleDrop(event: DragEvent) {
    event.preventDefault();
    dragover = false;

    const files = event.dataTransfer?.files;
    if (files && files[0]) {
      selectedFile = files[0];
    }
  }

  async function uploadAndGenerate() {
    if (!selectedFile) {
      console.error("No file selected");
      return;
    }

    // APIキーをチェック（localStorageから取得）
    const defaultProvider = getDefaultProvider() || "openai";
    const apiKey = getApiKey(defaultProvider);
    if (!apiKey) {
      alert("⚠️ LLMプロバイダーのAPIキーが設定されていません。\n設定画面からAPIキーを設定してください。");
      goto("/settings");
      return;
    }

    console.log("Uploading file:", selectedFile.name, selectedFile.type, selectedFile.size);
    
    isUploading = true;
    try {
      console.log("Creating FormData...");
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("target_duration", targetDuration.toString());
      // 選択されたスピーカー情報を取得
      const speaker1 = availableSpeakers.find(
        (s) => s.style_id === selectedSpeaker1Id
      );
      const speaker2 = availableSpeakers.find(
        (s) => s.style_id === selectedSpeaker2Id
      );

      formData.append("speaker1_id", selectedSpeaker1Id.toString());
      formData.append(
        "speaker1_name",
        speaker1 ? speaker1.speaker_name : "四国めたん"
      );
      formData.append("speaker1_speed", speaker1Speed.toString());
      formData.append("speaker2_id", selectedSpeaker2Id.toString());
      formData.append(
        "speaker2_name",
        speaker2 ? speaker2.speaker_name : "ずんだもん"
      );
      formData.append("speaker2_speed", speaker2Speed.toString());

      // 会話スタイル情報を追加
      const selectedStyle = conversationStyles.find(
        (s) => s.id === selectedConversationStyle
      );
      formData.append("conversation_style", selectedConversationStyle);
      formData.append(
        "conversation_style_prompt",
        selectedStyle ? selectedStyle.prompt : ""
      );
      
      // ナレッジファイルを追加
      if (knowledgeFile) {
        formData.append("knowledge_file", knowledgeFile);
      }
      
      // APIキーを追加（localStorageから取得）
      formData.append("api_key", apiKey);
      formData.append("provider", defaultProvider);

      console.log("Sending upload request...");
      const response = await fetch("/api/jobs/upload", {
        method: "POST",
        body: formData,
      });
      console.log("Upload response received:", response.status);

      if (!response.ok) {
        const errorText = await response.text();
        console.error("アップロードエラー:", response.status, errorText);
        let errorMessage = "アップロードに失敗しました";
        try {
          const errorJson = JSON.parse(errorText);
          errorMessage = errorJson.detail || errorMessage;
        } catch (e) {
          // JSONパースエラーの場合はテキストをそのまま使用
          if (errorText) {
            errorMessage = errorText;
          }
        }
        throw new Error(errorMessage);
      }

      const result = await response.json();
      currentJob = {
        job_id: result.job_id,
        status: "processing",
        progress: 0,
      };

      // 進行状況画面に切り替える（重要！）
      currentStep = "dialogue";

      // ステータス監視開始（対話生成は既にサーバー側で行われる）
      pollJobStatus(result.job_id);
    } catch (error) {
      console.error("エラー:", error);
      alert("アップロードに失敗しました");
    } finally {
      isUploading = false;
    }
  }

  async function generateDialogue(jobId: string, regenerate = false) {
    try {
      if (regenerate) {
        console.log("再生成開始:", {
          jobId,
          additionalPrompt,
          currentJobStatus: currentJob?.status,
          isRegenerating,
        });
        isRegenerating = true;
        await tick(); // UIの更新を強制
      }

      // APIキーを取得（localStorageから）
      const defaultProvider = getDefaultProvider() || "openai";
      const apiKey = getApiKey(defaultProvider);

      const response = await fetch(`/api/jobs/${jobId}/generate-dialogue`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          job_id: jobId,
          additional_prompt: regenerate ? additionalPrompt : null,
          api_key: apiKey,  // APIキーをリクエストに含める
          provider: defaultProvider,  // プロバイダーも含める
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || "対話生成開始に失敗しました");
      }

      // 進捗監視開始
      pollJobStatus(jobId);
    } catch (error) {
      console.error("エラー:", error);
      alert(error.message || "対話生成に失敗しました");
      if (currentJob) {
        currentJob.error = error.message || "対話生成に失敗しました";
      }
      isRegenerating = false;
    }
  }

  async function startVideoGeneration(jobId: string) {
    try {
      // 既存のエラー表示をクリア
      if (currentJob) {
        currentJob.error = "";
      }

      // 編集中の場合は先に編集を終了
      if (editingDialogue) {
        editingDialogue = false;
        await tick(); // UIの更新を待つ
      }

      // 対話データがあれば必ず保存（編集された可能性があるため）
      if (dialogueData) {
        await updateDialogue(jobId);
        // 保存完了を待つ
        await new Promise((resolve) => setTimeout(resolve, 500));
      }

      const formData = new FormData();
      formData.append("bgm_enabled", bgmEnabled.toString());
      if (bgmPath) {
        formData.append("bgm_path", bgmPath);
      }
      formData.append("bgm_volume", bgmVolume.toString());
      formData.append("transition_type", transitionType);
      formData.append("transition_duration", transitionDuration.toString());

      const response = await fetch(`/api/jobs/${jobId}/generate-video`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("動画生成開始に失敗しました");
      }

      currentStep = "video";
      // 進捗監視開始
      pollJobStatus(jobId);
    } catch (error) {
      console.error("エラー:", error);
      if (currentJob) {
        currentJob.error = "動画生成に失敗しました";
      }
    }
  }

  async function loadDialogue(jobId: string, forceReload = false) {
    try {
      console.log("対話データ読み込み開始:", {
        jobId,
        forceReload,
        isRegenerating,
      });

      // キャッシュを無効化するためのタイムスタンプを追加
      const timestamp = forceReload || isRegenerating ? `?t=${Date.now()}` : "";

      // 対話データを取得
      const dialogueResponse = await fetch(
        `/api/jobs/${jobId}/dialogue${timestamp}`
      );
      if (!dialogueResponse.ok) {
        console.error("対話データ取得失敗:", dialogueResponse.status);
        return;
      }

      const dialogueResult: DialogueResponse = await dialogueResponse.json();
      console.log("Raw dialogueResult:", dialogueResult);
      console.log(
        "dialogue_data keys before assignment:",
        Object.keys(dialogueResult.dialogue_data)
      );

      // Svelteの反応性を確実にするため、新しいオブジェクトとして割り当て
      dialogueData = { ...dialogueResult.dialogue_data };
      estimatedDuration = dialogueResult.estimated_duration;

      // デバッグ用ログ
      console.log(
        "対話データ取得成功:",
        Object.keys(dialogueData).length + "スライド"
      );
      console.log("推定動画時間:", estimatedDuration?.formatted);
      console.log("dialogueData after assignment:", dialogueData);
      console.log("dialogueData keys:", Object.keys(dialogueData));

      // スライド画像も取得
      const slidesResponse = await fetch(
        `/api/jobs/${jobId}/slides${timestamp}`
      );
      if (slidesResponse.ok) {
        slides = await slidesResponse.json();
        console.log("スライド画像取得成功:", slides.length + "枚");
      }

      // 指示履歴も取得
      await loadInstructionHistory(jobId);

      // メタデータも取得
      await loadJobMetadata(jobId);

      // 重要度設定も取得（対話データ読み込み後に実行）
      // 重要度が設定されていない場合は、デフォルト値（1.0）を設定
      if (dialogueData) {
        // まずデフォルト値を設定
        slideImportance = {};
        for (const slideKey of Object.keys(dialogueData)) {
          const slideNum = parseInt(slideKey.split("_")[1]);
          slideImportance[slideNum] = 1.0;
        }
        // サーバーから取得した重要度で上書き
        await loadSlideImportance(jobId);
      }

      currentStep = "dialogue";
      console.log("currentStep更新:", currentStep);

      // 強制的にUIを更新
      await tick();
    } catch (error) {
      console.error("対話データ取得エラー:", error);
    }
  }

  async function loadInstructionHistory(jobId: string) {
    try {
      const response = await fetch(`/api/jobs/${jobId}/instruction-history`);
      if (response.ok) {
        const data = await response.json();
        instructionHistory = data.history || {};
        console.log("指示履歴取得成功:", instructionHistory);
      }
    } catch (error) {
      console.error("指示履歴取得エラー:", error);
    }
  }

  async function loadJobMetadata(jobId: string) {
    try {
      const response = await fetch(`/api/jobs/${jobId}/metadata`);
      if (response.ok) {
        currentJobMetadata = await response.json();
        console.log("メタデータ取得成功:", currentJobMetadata);
      }
    } catch (error) {
      console.error("メタデータ取得エラー:", error);
    }
  }

  async function loadSlideImportance(jobId: string) {
    try {
      const response = await fetch(`/api/jobs/${jobId}/slide-importance`);
      if (response.ok) {
        const importanceData = await response.json();
        // サーバーから取得した重要度で上書き（既存のデフォルト値を保持）
        for (const [key, value] of Object.entries(importanceData)) {
          const slideNum = parseInt(key);
          slideImportance[slideNum] = value as number;
        }
        console.log("重要度設定取得成功:", slideImportance);
      } else {
        // 重要度が設定されていない場合は既に設定されたデフォルト値（1.0）を使用
        console.log("重要度設定なし、デフォルト値を使用");
      }
    } catch (error) {
      console.error("重要度設定取得エラー:", error);
      // エラー時は既に設定されたデフォルト値を使用
    }
  }

  async function saveSlideImportance(jobId: string) {
    if (!currentJob) return;
    
    try {
      isSavingImportance = true;
      const response = await fetch(`/api/jobs/${jobId}/slide-importance`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          job_id: jobId,
          importance_map: slideImportance,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || "重要度設定の保存に失敗しました");
      }

      const result = await response.json();
      console.log("重要度設定保存成功:", result);
      
      // 重要度が変更されたので、対話を再生成する必要があることをユーザーに通知
      // （オプション：自動再生成も可能）
    } catch (error) {
      console.error("重要度設定保存エラー:", error);
      alert(error.message || "重要度設定の保存に失敗しました");
    } finally {
      isSavingImportance = false;
    }
  }

  // 重要度変更時に自動保存（デバウンス付き）
  let saveImportanceTimeout: ReturnType<typeof setTimeout> | null = null;
  function onImportanceChange(jobId: string) {
    if (saveImportanceTimeout) {
      clearTimeout(saveImportanceTimeout);
    }
    saveImportanceTimeout = setTimeout(() => {
      saveSlideImportance(jobId);
    }, 1000); // 1秒後に自動保存
  }

  // 重要度に基づいて各スライドの推定時間を計算
  function calculateSlideDuration(slideNum: number): number {
    if (!dialogueData) return 0;
    
    const slideKey = `slide_${slideNum}`;
    const dialogues = dialogueData[slideKey] || [];
    
    // 文字数を計算
    let totalChars = 0;
    for (const dialogue of dialogues) {
      totalChars += dialogue.text.length;
    }
    
    // 読み上げ速度（文字/秒）
    const charsPerSecond = 5.5; // 330文字/分 ÷ 60秒
    
    // 基本時間
    const baseDuration = totalChars / charsPerSecond;
    
    // 重要度を適用
    const importance = slideImportance[slideNum] || 1.0;
    const adjustedDuration = baseDuration * importance;
    
    // 対話間の間隔を追加（0.3秒 × 対話数）
    const pauseTime = dialogues.length * 0.3;
    
    return adjustedDuration + pauseTime;
  }

  // 総時間を計算
  function calculateTotalDuration(): number {
    if (!dialogueData) return 0;
    
    let total = 0;
    for (const slideKey of Object.keys(dialogueData)) {
      const slideNum = parseInt(slideKey.split("_")[1]);
      total += calculateSlideDuration(slideNum);
    }
    
    // スライド間の間隔を追加（0.5秒 × スライド数）
    const slideCount = Object.keys(dialogueData).length;
    total += slideCount * 0.5;
    
    return total;
  }

  function formatDuration(seconds: number): string {
    const minutes = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${minutes}分${secs}秒`;
  }

  async function updateDialogue(jobId: string, data?: DialogueData | null) {
    try {
      isUpdatingDialogue = true;
      const payload = data ?? dialogueData;
      if (!payload) return;

      const response = await fetch(`/api/jobs/${jobId}/dialogue`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          job_id: jobId,
          dialogue_data: payload,
        }),
      });

      if (!response.ok) {
        throw new Error("対話データ更新に失敗しました");
      }

      const result = await response.json();

      // 推定時間を更新
      if (result.estimated_duration) {
        estimatedDuration = result.estimated_duration;
      }

      console.log("対話データ更新成功");
    } catch (error) {
      console.error("対話データ更新エラー:", error);
    } finally {
      isUpdatingDialogue = false;
    }
  }

  async function pollJobStatus(jobId: string) {
    console.log("ポーリング開始:", { jobId, currentStep });
    const poll = async () => {
      try {
        // 対話データ更新中はポーリングをスキップ
        if (isUpdatingDialogue) {
          setTimeout(poll, 3000);
          return;
        }

        const response = await fetch(`/api/jobs/${jobId}/status`);
        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          const errorMessage = errorData.detail || `ステータス取得エラー (${response.status})`;
          throw new Error(errorMessage);
        }

        const job = await response.json();
        currentJob = job;
        console.log("ジョブステータス:", {
          status: job.status,
          progress: job.progress,
          message: job.message,
          dialogueData: !!dialogueData,
          currentStep,
          editingDialogue,
        });

        if (job.status === "dialogue_ready" || job.status === "slides_ready") {
          // 対話編集画面で編集中の場合は、データを再読み込みしない
          if (currentStep === "dialogue" && editingDialogue) {
            console.log("編集中のため、データ再読み込みをスキップ");
            return; // ポーリング停止
          }

          if (!dialogueData || isRegenerating) {
            console.log(
              `${job.status}検知、対話データ読み込み開始 (再生成: ${isRegenerating})`
            );
            // 対話データを読み込む
            await loadDialogue(jobId, true); // 強制リロード

            // 対話データ生成完了（全体調整とカタカナ変換も含む）
            console.log("対話データ生成完了（全体調整とカタカナ変換済み）");

            isRegenerating = false;
            return; // ポーリング停止
          }
        } else if (job.status === "completed") {
          console.log("処理完了:", job.status);
          isRegenerating = false;
          return; // 完了
        } else if (job.status === "failed") {
          console.log("処理失敗:", job.status);
          isRegenerating = false;
          // エラー表示を設定
          if (currentJob) {
            currentJob.error = getDisplayError(job) || "処理に失敗しました";
          }
          return; // ポーリング停止
        }

        // dialogue編集画面で対話データが既に存在する場合は、generating_dialogue以外はポーリング不要
        if (
          currentStep === "dialogue" &&
          dialogueData &&
          job.status !== "generating_dialogue"
        ) {
          return;
        }

        // 3秒後に再試行
        setTimeout(poll, 3000);
      } catch (error) {
        console.error("ステータス取得エラー:", error);
        // エラー表示を設定
        if (currentJob) {
          currentJob.error = error.message || "ステータスの取得に失敗しました";
        }
        // エラー発生時もポーリングを継続（ネットワークエラーの可能性）
        setTimeout(poll, 5000); // 少し長めの間隔で再試行
      }
    };

    poll();
  }

  function resetForm() {
    selectedFile = null;
    currentJob = null;
    isUploading = false;
    dialogueData = null;
    estimatedDuration = null;
    editingDialogue = false;
    additionalPrompt = "";
    currentStep = "upload";
    isRegenerating = false;
    showHistoryForSlide = null;
    targetDuration = 10; // デフォルトに戻す
    slideImportance = {}; // 重要度設定をリセット
  }

  function addDialogueItem(slideKey: string) {
    if (!dialogueData) return;
    // 最後の発話者と逆のスピーカーを選択
    const lastSpeaker =
      dialogueData[slideKey].length > 0
        ? dialogueData[slideKey][dialogueData[slideKey].length - 1].speaker
        : "speaker2";
    const nextSpeaker = lastSpeaker === "speaker1" ? "speaker2" : "speaker1";

    dialogueData[slideKey] = [
      ...dialogueData[slideKey],
      { speaker: nextSpeaker, text: "" },
    ];
  }

  function removeDialogueItem(slideKey: string, index: number) {
    if (!dialogueData) return;
    dialogueData[slideKey] = dialogueData[slideKey].filter(
      (_, i) => i !== index
    );
  }

  function openImageModal(imageUrl: string) {
    modalImageUrl = imageUrl;
  }

  function closeImageModal() {
    modalImageUrl = null;
  }

  function toggleSlideHistory(slideKey: string) {
    if (showHistoryForSlide === slideKey) {
      showHistoryForSlide = null;
    } else {
      showHistoryForSlide = slideKey;
    }
  }

  async function downloadCSV(jobId: string) {
    try {
      const response = await fetch(`/api/jobs/${jobId}/dialogue/csv`);
      if (!response.ok) {
        throw new Error("CSVダウンロードに失敗しました");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dialogue_${jobId}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (error) {
      console.error("CSVダウンロードエラー:", error);
      alert("CSVダウンロードに失敗しました");
    }
  }

  async function handleCSVUpload(event: Event) {
    const target = event.target as HTMLInputElement;
    if (!target.files || !target.files[0] || !currentJob) return;

    const file = target.files[0];
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(
        `/api/jobs/${currentJob.job_id}/dialogue/csv`,
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "CSVアップロードに失敗しました");
      }

      const result = await response.json();

      // 推定時間を更新
      if (result.estimated_duration) {
        estimatedDuration = result.estimated_duration;
      }

      alert(`${result.message}`);

      // 対話データを再読み込み
      await loadDialogue(currentJob.job_id, true);
    } catch (error) {
      console.error("CSVアップロードエラー:", error);
      alert(error.message || "CSVアップロードに失敗しました");
    } finally {
      // ファイル選択をリセット
      target.value = "";
    }
  }
</script>

<svelte:head>
  <title>Keki AI - PDF to Video Generator</title>
</svelte:head>


<main class="container">
  <header>
    <div class="header-content">
      <div>
        <h1>Keki AI</h1>
        <p>PDFから動画を生成</p>
      </div>
      <div class="header-actions">
        <a href="/history" class="settings-link"> 📋 履歴 </a>
        <a href="/settings" class="settings-link"> ⚙️ LLM設定 </a>
      </div>
    </div>
  </header>

  {#if currentStep === "upload"}
    <section class="upload-section">
      {#if !selectedFile}
        <div
          class="dropzone"
          class:dragover
          role="button"
          tabindex="0"
          on:dragover|preventDefault={() => (dragover = true)}
          on:dragleave={() => (dragover = false)}
          on:drop={handleDrop}
        >
          <div class="drop-content">
            <div class="upload-icon">📁</div>
            <h3>PDFファイルをアップロード</h3>
            <p>ドラッグ&ドロップまたはクリックしてファイルを選択</p>

            <input
              type="file"
              accept=".pdf"
              on:change={handleFileSelect}
              class="file-input"
              id="file-input"
            />
            <label for="file-input" class="file-label"> ファイルを選択 </label>
          </div>
        </div>
      {/if}

      {#if selectedFile}
        <div class="file-info">
          <div class="file-details">
            <strong>選択ファイル:</strong>
            {selectedFile.name}
            <br />
            <strong>サイズ:</strong>
            {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
          </div>

          <div class="duration-setting">
            <label for="target-duration">目安動画時間:</label>
            <input
              type="number"
              id="target-duration"
              bind:value={targetDuration}
              min="1"
              max="60"
              step="1"
            />
            <span>分</span>
          </div>

          <div class="conversation-style-settings">
            <h4>会話スタイル</h4>
            <div class="style-grid">
              {#each conversationStyles as style}
                <div class="style-option">
                  <input
                    type="radio"
                    id="style-{style.id}"
                    name="conversationStyle"
                    value={style.id}
                    bind:group={selectedConversationStyle}
                  />
                  <label for="style-{style.id}" class="style-label">
                    <span class="style-name">{style.name}</span>
                    <span class="style-description">{style.description}</span>
                  </label>
                </div>
              {/each}
            </div>
          </div>

          <div class="speaker-settings">
            <h4>キャラクター設定</h4>
            <button
              class="recommendation-toggle"
              on:click={() => (showRecommendations = !showRecommendations)}
              disabled={playingSampleId !== null}
            >
              💼 ビジネス向けおすすめを見る
            </button>

            {#if showRecommendations}
              <div class="recommendations">
                <h5>ビジネス向けおすすめ組み合わせ</h5>
                {#each businessRecommendations as rec}
                  <div class="recommendation-item">
                    <div class="rec-header">
                      <strong>{rec.name}</strong>
                      <button
                        class="apply-btn"
                        on:click={() => applyRecommendation(rec)}
                        disabled={playingSampleId !== null}
                      >
                        この組み合わせを使う
                      </button>
                    </div>
                    <p class="rec-description">{rec.description}</p>
                    <p class="rec-speakers">
                      説明役: {rec.speaker1.name} / 聞き役: {rec.speaker2.name}
                    </p>
                  </div>
                {/each}
              </div>
            {/if}

            {#if speakersLoading}
              <p>読み込み中...</p>
            {:else}
              <div class="speaker-row">
                <label for="speaker1">話者1（説明役）:</label>
                <select
                  id="speaker1"
                  bind:value={selectedSpeaker1Id}
                  disabled={playingSampleId !== null}
                >
                  {#each availableSpeakers as speaker}
                    <option value={speaker.style_id}>
                      {speaker.display_name}
                    </option>
                  {/each}
                </select>
                <button
                  class="sample-btn"
                  class:loading={playingSampleId === selectedSpeaker1Id}
                  on:click={() => {
                    const speaker = availableSpeakers.find(
                      (s) => s.style_id === selectedSpeaker1Id
                    );
                    if (speaker)
                      playVoiceSample(
                        selectedSpeaker1Id,
                        speaker.speaker_name,
                        speaker1Speed
                      );
                  }}
                  disabled={playingSampleId !== null}
                  title="サンプルボイスを再生"
                >
                  {#if playingSampleId === selectedSpeaker1Id}
                    <span class="spinner"></span>
                  {:else}
                    🔊
                  {/if}
                </button>
              </div>
              <div class="speed-row">
                <label for="speaker1-speed"
                  >話者1の速度: {speaker1Speed.toFixed(1)}倍</label
                >
                <input
                  type="range"
                  id="speaker1-speed"
                  bind:value={speaker1Speed}
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  class="speed-slider"
                />
              </div>
              <div class="speaker-row">
                <label for="speaker2">話者2（聞き役）:</label>
                <select
                  id="speaker2"
                  bind:value={selectedSpeaker2Id}
                  disabled={playingSampleId !== null}
                >
                  {#each availableSpeakers as speaker}
                    <option value={speaker.style_id}>
                      {speaker.display_name}
                    </option>
                  {/each}
                </select>
                <button
                  class="sample-btn"
                  class:loading={playingSampleId === selectedSpeaker2Id}
                  on:click={() => {
                    const speaker = availableSpeakers.find(
                      (s) => s.style_id === selectedSpeaker2Id
                    );
                    if (speaker)
                      playVoiceSample(
                        selectedSpeaker2Id,
                        speaker.speaker_name,
                        speaker2Speed
                      );
                  }}
                  disabled={playingSampleId !== null}
                  title="サンプルボイスを再生"
                >
                  {#if playingSampleId === selectedSpeaker2Id}
                    <span class="spinner"></span>
                  {:else}
                    🔊
                  {/if}
                </button>
              </div>
              <div class="speed-row">
                <label for="speaker2-speed"
                  >話者2の速度: {speaker2Speed.toFixed(1)}倍</label
                >
                <input
                  type="range"
                  id="speaker2-speed"
                  bind:value={speaker2Speed}
                  min="0.5"
                  max="2.0"
                  step="0.1"
                  class="speed-slider"
                />
              </div>
            {/if}
          </div>

          <div class="knowledge-section">
            <button
              class="knowledge-toggle"
              on:click={() => (knowledgeExpanded = !knowledgeExpanded)}
              type="button"
            >
              <span class="toggle-icon">{knowledgeExpanded ? '▼' : '▶'}</span>
              📚 補助ナレッジを追加（オプション）
            </button>
            
            {#if knowledgeExpanded}
              <div class="knowledge-content">
                <p class="knowledge-description">
                  スライドに記載されていない補足情報を含むファイルをアップロードできます。
                  AIはこの情報を参考にしますが、あくまでも<strong>スライドの内容が主体</strong>となり、
                  スライドに書かれていない内容については話しません。
                </p>
                <p class="knowledge-supported-formats">
                  <strong>対応ファイル形式:</strong> .pdf, .docx, .pptx, .md, .txt, .rtf, .odt, .csv
                </p>
                <div class="knowledge-upload-area">
                  {#if !knowledgeFile}
                    <div class="knowledge-dropzone">
                      <div class="knowledge-upload-icon">📄</div>
                      <p>ナレッジファイルをアップロード</p>
                      <input
                        type="file"
                        accept=".pdf,.docx,.pptx,.md,.txt,.rtf,.odt,.csv"
                        on:change={handleKnowledgeFileSelect}
                        class="knowledge-file-input"
                        id="knowledge-file-input"
                      />
                      <label for="knowledge-file-input" class="knowledge-file-label">
                        ファイルを選択
                      </label>
                    </div>
                  {:else}
                    <div class="knowledge-file-info">
                      <div class="knowledge-file-name">
                        📄 {knowledgeFile.name}
                      </div>
                      <div class="knowledge-file-size">
                        ({(knowledgeFile.size / 1024).toFixed(1)} KB)
                      </div>
                      <button
                        class="knowledge-remove-btn"
                        on:click={() => knowledgeFile = null}
                        type="button"
                      >
                        ✕
                      </button>
                    </div>
                  {/if}
                </div>
              </div>
            {/if}
          </div>

          {#if dialogueData && currentJob}
            <button
              class="back-to-dialogue-btn"
              on:click={() => {
                currentStep = "dialogue";
              }}
            >
              📝 スクリプト編集に戻る
            </button>
          {:else}
            <button
              class="generate-btn"
              on:click={uploadAndGenerate}
              disabled={isUploading || playingSampleId !== null}
            >
              {isUploading ? "処理中..." : "📝 対話スクリプト生成"}
            </button>
          {/if}

          <button class="reset-btn" on:click={resetForm}> リセット </button>
        </div>
      {/if}
    </section>
  {:else if currentStep === "dialogue" && dialogueData}
    <section class="dialogue-section">
      <h3>📝 対話スクリプト編集</h3>

      <div class="duration-estimate">
        <span class="duration-icon">⏱️</span>
        <span class="duration-text">
          推定動画時間: <strong>{formatDuration(calculateTotalDuration())}</strong>
          {#if currentJobMetadata?.target_duration}
            <span class="target-duration">
              (目標: {currentJobMetadata.target_duration}分)
            </span>
          {/if}
        </span>
        {#if calculateTotalDuration() > (currentJobMetadata?.target_duration || 10) * 60}
          <span class="duration-warning">⚠️ 目標時間を超過しています</span>
        {/if}
      </div>

      <!-- 段階的プレビュー：制作フローの現在位置 -->
      {#if currentJob}
        {@const sc = (currentJob.status_code || "").toString()}
        {@const st = currentJob.status || ""}
        {@const audioPhaseDone =
          st === "completed" || sc.includes("VIDEO") || sc === "AUDIO_COMPLETED"}
        {@const audioPhaseActive = !audioPhaseDone && sc.includes("AUDIO")}
        <div
          class="preview-pipeline"
          role="navigation"
          aria-label="制作フローの進行状況"
        >
          <div class="preview-pipeline-title">📍 制作ステップ</div>
          <div class="preview-pipeline-steps">
            <span
              class="pipeline-step {slides.length > 0
                ? 'done'
                : st === 'processing'
                  ? 'active'
                  : 'pending'}"
            >
              ① PDF・スライド
            </span>
            <span class="pipeline-arrow">→</span>
            <span
              class="pipeline-step {dialogueData
                ? currentStep === 'dialogue'
                  ? 'active'
                  : 'done'
                : 'pending'}"
            >
              ② 対話スクリプト
            </span>
            <span class="pipeline-arrow">→</span>
            <span
              class="pipeline-step {audioPhaseDone
                ? 'done'
                : audioPhaseActive
                  ? 'active'
                  : dialogueData
                    ? 'pending'
                    : 'pending'}"
            >
              ③ 音声合成
            </span>
            <span class="pipeline-arrow">→</span>
            <span
              class="pipeline-step {st === 'completed'
                ? 'done'
                : sc.includes('VIDEO') || currentStep === 'video'
                  ? 'active'
                  : 'pending'}"
            >
              ④ 動画
            </span>
          </div>
        </div>
      {/if}

      <div class="dialogue-controls">
        <button
          class="back-to-settings-btn"
          on:click={() => {
            const confirmed = confirm(
              "キャラクター設定に戻りますか？\n\n現在の対話スクリプトの内容は保持されますが、編集中の変更は失われる可能性があります。"
            );
            if (confirmed) {
              currentStep = "upload";
              // currentJobとdialogueDataは保持して、後で戻れるようにする
              editingDialogue = false;
              isRegenerating = false;
            }
          }}
        >
          ⬅️ キャラクター設定に戻る
        </button>
        <button
          class="csv-download-btn"
          on:click={async () => {
            if (!currentJob) return;
            // 編集中でなくても、念のためデータを保存
            if (dialogueData) {
              await updateDialogue(currentJob.job_id);
              // 保存完了を待つ
              await new Promise((resolve) => setTimeout(resolve, 500));
            }
            await downloadCSV(currentJob.job_id);
          }}
        >
          📥 CSVダウンロード
        </button>
        <button
          class="csv-upload-btn"
          on:click={() => document.getElementById("csv-upload-input")?.click()}
        >
          📤 CSVアップロード
        </button>
        <input
          id="csv-upload-input"
          type="file"
          accept=".csv"
          style="display: none"
          on:change={handleCSVUpload}
        />
        <button
          class="settings-toggle-btn"
          on:click={() => showVideoSettings = !showVideoSettings}
        >
          {showVideoSettings ? "⚙️ 動画設定を閉じる" : "⚙️ 動画設定を開く"}
        </button>
        <button
          class="generate-btn"
          on:click={() => currentJob && startVideoGeneration(currentJob.job_id)}
        >
          🎥 動画生成開始
        </button>
      </div>

      {#if showVideoSettings}
        <div class="video-settings-panel">
          <h4>🎬 動画設定</h4>
          
          <!-- BGM設定 -->
          <div class="setting-group">
            <label class="checkbox-label">
              <input
                type="checkbox"
                bind:checked={bgmEnabled}
              />
              <span>背景音楽（BGM）を有効にする</span>
            </label>
            
            {#if bgmEnabled}
              <div class="setting-subgroup">
                <label for="bgm-path">BGMファイルパス（bgm/ディレクトリからの相対パス）:</label>
                <input
                  id="bgm-path"
                  type="text"
                  bind:value={bgmPath}
                  placeholder="例: background_music.mp3"
                  class="setting-input"
                />
                <small class="setting-hint">bgm/ディレクトリ内のファイル名を指定してください</small>
                
                <label for="bgm-volume">BGM音量: {(bgmVolume * 100).toFixed(0)}%</label>
                <input
                  id="bgm-volume"
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  bind:value={bgmVolume}
                  class="setting-slider"
                />
              </div>
            {/if}
          </div>

          <!-- 転場効果設定 -->
          <div class="setting-group">
            <label for="transition-type">転場効果:</label>
            <select
              id="transition-type"
              bind:value={transitionType}
              class="setting-select"
            >
              <option value="crossfade">クロスフェード（推奨）</option>
              <option value="fade">フェード</option>
              <option value="slide">スライド</option>
              <option value="zoom">ズーム</option>
              <option value="none">転場なし</option>
            </select>
            
            {#if transitionType !== "none"}
              <label for="transition-duration">転場時間: {transitionDuration.toFixed(1)}秒</label>
              <input
                id="transition-duration"
                type="range"
                min="0.1"
                max="1.0"
                step="0.1"
                bind:value={transitionDuration}
                class="setting-slider"
              />
            {/if}
          </div>
        </div>
      {/if}

      <div class="edit-notice">
        <span class="notice-icon">⚠️</span>
        <span class="notice-text">
          <strong>編集時の注意：</strong>英単語はカタカナで入力してください。
          アルファベットのまま入力すると音声生成時に正しく読み上げられない場合があります。
          <br />
          例: API → エーピーアイ、Claude → クロード、USB → ユーエスビー、CLI → シーエルアイ
        </span>
      </div>

      <div class="additional-prompt-section">
        <label for="additional-prompt">
          AIへの追加指示（再生成時に使用）
          {#if editingDialogue}
            <span style="color: #999;">※編集中は使用できません</span>
          {/if}
          :</label
        >
        <textarea
          id="additional-prompt"
          bind:value={additionalPrompt}
          placeholder="例: 1枚目のスライドをもっとカジュアルに / 全体的に初心者向けに / 最初と最後のスライドを修正"
          rows="3"
          disabled={isRegenerating || editingDialogue}
        ></textarea>
        <button
          class="regenerate-btn"
          on:click={() =>
            currentJob && generateDialogue(currentJob.job_id, true)}
          disabled={currentJob?.status === "generating_dialogue" ||
            isRegenerating ||
            !additionalPrompt.trim() ||
            editingDialogue}
        >
          {isRegenerating ? "⏳ 再生成中..." : "🔄 スクリプト再生成"}
        </button>
        {#if isRegenerating && currentJob}
          <div class="regeneration-status">
            <div class="status-message">
              🤖 {getDisplayMessage(currentJob) || "AIが修正対象を判断中..."}
            </div>
            <div class="progress-bar">
              <div
                class="progress-fill"
                style="width: {currentJob.progress}%"
              ></div>
            </div>
          </div>
        {/if}
      </div>

      <div class="edit-controls">
        <div class="edit-controls-left">
          <div class="view-mode-toggle">
            <button
              class="view-btn {viewMode === 'list' ? 'active' : ''}"
              on:click={() => viewMode = 'list'}
              title="リスト表示"
            >
              📋 リスト
            </button>
            <button
              class="view-btn {viewMode === 'timeline' ? 'active' : ''}"
              on:click={() => viewMode = 'timeline'}
              title="タイムライン表示"
            >
              ⏱️ タイムライン
            </button>
          </div>
          <p class="view-mode-preview-hint">
            💡 スライド拡大プレビュー・セリフの音声試聴は「リスト」表示で利用できます
          </p>
        </div>
        <button
          class="edit-btn"
          on:click={async () => {
            if (editingDialogue && currentJob) {
              // 編集を終了する前に保存
              await updateDialogue(currentJob.job_id);
            }
            const enteringEdit = !editingDialogue;
            editingDialogue = !editingDialogue;
            if (enteringEdit) {
              setFirstSlideAsPreview();
            }
          }}
        >
          {editingDialogue ? "編集を終了" : "✏️ スクリプトを編集"}
        </button>
      </div>

      {#if viewMode === 'timeline' && dialogueData}
        <TimelineEditor
          {dialogueData}
          {slides}
          {currentJobMetadata}
          jobId={currentJob?.job_id || null}
          onUpdate={(updatedData) => {
            dialogueData = updatedData;
            if (currentJob) {
              updateDialogue(currentJob.job_id, updatedData);
            }
          }}
        />
      {:else}
      {#if editingDialogue && slides.length > 0}
        <div class="realtime-slide-preview">
          <div class="realtime-preview-header">
            <span class="realtime-preview-title">👁️ リアルタイムスライドプレビュー</span>
            <span class="realtime-preview-hint"
              >テキストを編集するスライドのエリアをクリックすると、そのスライドを大きく表示します</span
            >
          </div>
          {#if previewSlideKey}
            {@const previewNum = parseInt(previewSlideKey.split("_")[1])}
            {@const previewSlide = slides.find(
              (s) => s.slide_number === previewNum
            )}
            {#if previewSlide}
              <div class="realtime-preview-body">
                <img
                  src={previewSlide.url}
                  alt="スライド {previewNum}"
                  class="realtime-preview-image"
                />
              </div>
            {/if}
          {:else}
            <p class="realtime-preview-empty">スライドを選択してください</p>
          {/if}
        </div>
      {/if}
      <div class="dialogue-list">
        {#each Object.entries(dialogueData) as [slideKey, dialogues]}
          {@const slideNum = parseInt(slideKey.split("_")[1])}
          {@const slideHistory = instructionHistory[slideKey] || []}
          <div class="slide-dialogue">
            <div class="slide-header">
              {#if slides.length > 0}
                {@const slide = slides.find((s) => s.slide_number === slideNum)}
                {#if slide}
                  <img
                    src={slide.url}
                    alt="Slide {slideNum}"
                    class="slide-thumbnail clickable"
                    on:click={() => openImageModal(slide.url)}
                    role="button"
                    tabindex="0"
                    on:keydown={(e) =>
                      e.key === "Enter" && openImageModal(slide.url)}
                  />
                {/if}
              {/if}
              <h4>{slideKey.replace("slide_", "スライド")}</h4>
              {#if slideHistory.length > 0}
                <button
                  class="history-toggle"
                  on:click={() => toggleSlideHistory(slideKey)}
                  title="指示履歴を表示"
                >
                  📝 履歴 ({slideHistory.length})
                </button>
              {/if}
            </div>
            
            <!-- 重要度調整UI -->
            <div class="importance-control">
              <div class="importance-label">
                <label for="importance-{slideNum}">重要度:</label>
                <span class="importance-value">{(slideImportance[slideNum] || 1.0).toFixed(1)}x</span>
                <span class="importance-duration">
                  (予定: {formatDuration(calculateSlideDuration(slideNum))})
                </span>
              </div>
              <div class="importance-slider-container">
                <input
                  type="range"
                  id="importance-{slideNum}"
                  min="0.5"
                  max="1.5"
                  step="0.1"
                  value={slideImportance[slideNum] || 1.0}
                  on:input={(e) => {
                    const value = parseFloat(e.currentTarget.value);
                    slideImportance[slideNum] = value;
                    if (currentJob) {
                      onImportanceChange(currentJob.job_id);
                    }
                  }}
                  class="importance-slider"
                />
                <div class="importance-labels">
                  <span class="importance-label-min">0.5x (簡潔)</span>
                  <span class="importance-label-default">1.0x (標準)</span>
                  <span class="importance-label-max">1.5x (詳細)</span>
                </div>
              </div>
            </div>
            {#if showHistoryForSlide === slideKey}
              <div class="instruction-history">
                <h5>再生成指示履歴:</h5>
                {#each slideHistory as hist, idx}
                  <div class="history-item">
                    <div class="history-timestamp">
                      {new Date(hist.timestamp).toLocaleString("ja-JP")}
                    </div>
                    <div class="history-instruction">
                      {hist.instruction}
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
            {#each dialogues as dialogue, index}
              <div
                class="dialogue-item"
                on:focusin={() => {
                  previewSlideKey = slideKey;
                }}
              >
                <div class="speaker-label {dialogue.speaker}">
                  {#if dialogue.speaker === "speaker1"}
                    {currentJobMetadata?.speaker1?.name || "話者1"}
                  {:else if dialogue.speaker === "speaker2"}
                    {currentJobMetadata?.speaker2?.name || "話者2"}
                  {:else if dialogue.speaker === "metan"}
                    四国めたん
                  {:else if dialogue.speaker === "zundamon"}
                    ずんだもん
                  {:else}
                    {dialogue.speaker}
                  {/if}
                </div>
                <div class="dialogue-item-main">
                  {#if editingDialogue}
                    <textarea
                      bind:value={dialogue.text}
                      class="dialogue-text-edit"
                      rows="2"
                      on:focus={() => {
                        previewSlideKey = slideKey;
                      }}
                    ></textarea>
                    <button
                      class="remove-btn"
                      on:click={() => removeDialogueItem(slideKey, index)}
                    >
                      ✕
                    </button>
                  {:else}
                    <div class="dialogue-text">{dialogue.text}</div>
                  {/if}
                  <button
                    type="button"
                    class="voice-preview-line-btn"
                    title="このセリフをVOICEVOXで試聴（全文合成前のプレビュー）"
                    disabled={voicePreviewKey === `${slideKey}_${index}` ||
                      !dialogue.text?.trim()}
                    on:click={() =>
                      previewDialogueLine(
                        slideKey,
                        index,
                        dialogue.text,
                        dialogue.speaker
                      )}
                  >
                    {voicePreviewKey === `${slideKey}_${index}`
                      ? "⏳"
                      : "🔊"} 試聴
                  </button>
                </div>
              </div>
            {/each}
            {#if editingDialogue}
              <button
                class="add-dialogue-btn"
                on:click={() => addDialogueItem(slideKey)}
              >
                ＋ セリフを追加
              </button>
            {/if}
          </div>
        {/each}
      </div>
      {/if}
    </section>
  {:else if currentJob && (isUploading || currentJob.status === "processing" || currentJob.status === "generating_dialogue" || currentStep === "video" || (currentStep === "dialogue" && !dialogueData))}
    <section class="progress-section">
      <div class="job-info">
        <h3>
          {currentStep === "video"
            ? "動画生成中..."
            : "対話スクリプト生成中..."}
        </h3>
        <div class="job-id">Job ID: {currentJob.job_id}</div>

        <div class="progress-bar">
          <div
            class="progress-fill"
            style="width: {currentJob.progress}%"
          ></div>
        </div>

        <div class="status-info">
          <div class="status">ステータス: {getDisplayStatus(currentJob)}</div>
          <div class="progress-text">{currentJob.progress}% 完了</div>
        </div>

        {#if getDisplayMessage(currentJob)}
          <div class="message">{getDisplayMessage(currentJob)}</div>
        {/if}

        {#if getDisplayError(currentJob)}
          <div class="error">❌ {getDisplayError(currentJob)}</div>
        {/if}
        
        {#if currentJob.error}
          <div class="error">❌ {currentJob.error}</div>
        {/if}

        {#if currentJob.status === "failed"}
          <div class="action-buttons">
            <button
              class="primary-btn"
              on:click={() => startVideoGeneration(currentJob.job_id)}
            >
              🔁 動画生成を再試行
            </button>
          </div>
        {/if}

        {#if currentJob.status === "completed" && currentJob.result_url}
          <div class="result">
            <h4>✅ 動画生成完了！</h4>
            <div class="download-section">
              <a href={currentJob.result_url} download class="download-btn">
                📥 動画をダウンロード
              </a>
              <video controls class="preview-video">
                <source src={currentJob.result_url} type="video/mp4" />
                お使いのブラウザは動画再生に対応していません。
              </video>
            </div>
            <div class="voicevox-credit-notice">
              <h5>⚠️ 重要：VOICEVOXクレジット表記について</h5>
              <p>
                この動画を公開する場合は、動画の概要欄や説明欄に以下のクレジット表記が必要です：
              </p>
              <div class="credit-example">
                {#if currentJobMetadata?.speaker1?.name}
                  <strong>VOICEVOX:{currentJobMetadata.speaker1.name}</strong><br />
                {:else}
                  <strong>VOICEVOX:四国めたん</strong><br />
                {/if}
                {#if currentJobMetadata?.speaker2?.name}
                  <strong>VOICEVOX:{currentJobMetadata.speaker2.name}</strong>
                {:else}
                  <strong>VOICEVOX:ずんだもん</strong>
                {/if}
              </div>
              <p class="credit-note">
                ※ 使用したキャラクター名を必ず記載してください。<br />
                ※ クレジット表記はVOICEVOXの利用規約で定められています。
              </p>
            </div>
            <div class="action-buttons">
              <button
                class="back-to-script-btn"
                on:click={() => {
                  if (currentJob && dialogueData) {
                    currentStep = "dialogue";
                  }
                }}
              >
                📝 スクリプトに戻る
              </button>
            </div>
          </div>
        {/if}

        <button class="new-job-btn" on:click={resetForm}>
          新しい動画を作成
        </button>
      </div>
    </section>
  {/if}

  <!-- APIキー警告ポップアップ -->
  {#if showApiKeyWarning}
    <div class="modal-overlay" on:click={() => (showApiKeyWarning = false)}>
      <div class="api-key-warning" on:click|stopPropagation>
        <h2>⚠️ LLMプロバイダーの設定が必要です</h2>
        <p>
          AIによる対話生成を利用するには、LLMプロバイダーのAPIキーを設定してください。
        </p>
        <div class="warning-actions">
          <a href="/settings" class="primary-btn"> ⚙️ 設定画面へ </a>
          <button
            class="secondary-btn"
            on:click={() => (showApiKeyWarning = false)}
          >
            後で設定
          </button>
        </div>
      </div>
    </div>
  {/if}
</main>

{#if modalImageUrl}
  <div
    class="modal-overlay"
    on:click={closeImageModal}
    role="button"
    tabindex="0"
    on:keydown={(e) => e.key === "Escape" && closeImageModal()}
  >
    <div class="modal-content" on:click|stopPropagation>
      <button class="modal-close" on:click={closeImageModal}>✕</button>
      <img src={modalImageUrl} alt="拡大画像" class="modal-image" />
    </div>
  </div>
{/if}

<style>
  .container {
    max-width: 1000px;
    margin: 0 auto;
    padding: 2rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      sans-serif;
  }

  header {
    margin-bottom: 3rem;
  }

  .header-content {
    display: flex;
    justify-content: space-between;
    align-items: center;
    width: 100%;
  }

  .header-content > div:first-child {
    text-align: center;
    flex: 1;
  }

  .header-content > div:last-child {
    flex-shrink: 0;
    display: flex;
    gap: 0.5rem;
  }

  .settings-link {
    background-color: #6b7280;
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 8px;
    text-decoration: none;
    font-size: 0.9rem;
    transition: background-color 0.3s ease;
    white-space: nowrap;
  }

  .settings-link:hover {
    background-color: #4b5563;
  }

  header h1 {
    font-size: 2.5rem;
    color: #2563eb;
    margin-bottom: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
  }


  header p {
    color: #6b7280;
    font-size: 1.1rem;
  }

  .upload-section {
    margin-bottom: 2rem;
  }

  .dropzone {
    border: 2px dashed #d1d5db;
    border-radius: 12px;
    padding: 3rem;
    text-align: center;
    transition: all 0.3s ease;
    background-color: #f9fafb;
  }

  .dropzone:hover,
  .dropzone.dragover {
    border-color: #2563eb;
    background-color: #eff6ff;
  }

  .upload-icon {
    font-size: 3rem;
    margin-bottom: 1rem;
  }

  .file-input {
    display: none;
  }

  .file-label {
    display: inline-block;
    background-color: #2563eb;
    color: white;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.3s ease;
    margin-top: 1rem;
  }

  .file-label:hover {
    background-color: #1d4ed8;
  }

  .file-info {
    margin-top: 2rem;
    padding: 1.5rem;
    background-color: #f3f4f6;
    border-radius: 8px;
  }

  .file-details {
    margin-bottom: 1rem;
    color: #374151;
  }

  .generate-btn {
    background-color: #10b981;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    font-size: 1rem;
    margin-right: 1rem;
    transition: background-color 0.3s ease;
  }

  .generate-btn:hover {
    background-color: #059669;
  }

  .generate-btn:disabled {
    background-color: #9ca3af;
    cursor: not-allowed;
  }

  .reset-btn,
  .new-job-btn {
    background-color: #6b7280;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    font-size: 1rem;
    transition: background-color 0.3s ease;
  }

  .reset-btn:hover,
  .new-job-btn:hover {
    background-color: #4b5563;
  }

  /* 対話編集セクション */
  .dialogue-section {
    max-width: 100%;
  }

  .duration-estimate {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background-color: #e0f2fe;
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 1.5rem;
    border: 1px solid #7dd3fc;
  }

  .duration-icon {
    font-size: 1.25rem;
  }

  .duration-text {
    color: #0369a1;
    font-size: 1rem;
  }

  .duration-text strong {
    font-weight: 600;
    color: #0c4a6e;
  }

  .target-duration {
    color: #6b7280;
    font-size: 0.9rem;
    margin-left: 0.5rem;
  }

  .duration-warning {
    color: #dc2626;
    font-size: 0.875rem;
    margin-left: 0.5rem;
    font-weight: 500;
  }

  /* 段階的プレビュー：制作ステップ表示 */
  .preview-pipeline {
    background: linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%);
    border: 1px solid #c4b5fd;
    border-radius: 10px;
    padding: 0.85rem 1rem;
    margin-bottom: 1.25rem;
  }

  .preview-pipeline-title {
    font-size: 0.8rem;
    font-weight: 600;
    color: #5b21b6;
    margin-bottom: 0.5rem;
  }

  .preview-pipeline-steps {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.35rem 0.25rem;
    font-size: 0.8rem;
  }

  .pipeline-step {
    padding: 0.25rem 0.5rem;
    border-radius: 6px;
    font-weight: 500;
    color: #6b7280;
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
  }

  .pipeline-step.done {
    color: #065f46;
    background: #d1fae5;
    border-color: #6ee7b7;
  }

  .pipeline-step.active {
    color: #1e40af;
    background: #dbeafe;
    border-color: #93c5fd;
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
  }

  .pipeline-step.pending {
    opacity: 0.85;
  }

  .pipeline-arrow {
    color: #9ca3af;
    font-size: 0.75rem;
    user-select: none;
  }

  /* 編集中のスライド拡大プレビュー */
  .realtime-slide-preview {
    background: #fff;
    border: 2px solid #a78bfa;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1.25rem;
    box-shadow: 0 4px 14px rgba(124, 58, 237, 0.12);
  }

  .realtime-preview-header {
    margin-bottom: 0.75rem;
  }

  .realtime-preview-title {
    display: block;
    font-weight: 700;
    color: #5b21b6;
    font-size: 1rem;
    margin-bottom: 0.25rem;
  }

  .realtime-preview-hint {
    font-size: 0.8rem;
    color: #6b7280;
    line-height: 1.4;
  }

  .realtime-preview-body {
    border-radius: 8px;
    overflow: hidden;
    background: #111827;
    text-align: center;
    max-height: 320px;
  }

  .realtime-preview-image {
    max-width: 100%;
    max-height: 320px;
    width: auto;
    height: auto;
    object-fit: contain;
    vertical-align: middle;
  }

  .realtime-preview-empty {
    font-size: 0.875rem;
    color: #9ca3af;
    margin: 0;
    padding: 1rem;
    text-align: center;
  }

  /* 重要度調整UI */
  .importance-control {
    background-color: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .importance-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
    font-size: 0.9rem;
  }

  .importance-label label {
    font-weight: 500;
    color: #374151;
  }

  .importance-value {
    font-weight: 600;
    color: #2563eb;
    font-size: 1rem;
  }

  .importance-duration {
    color: #6b7280;
    font-size: 0.875rem;
    margin-left: auto;
  }

  .importance-slider-container {
    position: relative;
  }

  .importance-slider {
    width: 100%;
    height: 8px;
    background: #e5e7eb;
    border-radius: 4px;
    outline: none;
    -webkit-appearance: none;
    margin-bottom: 0.5rem;
  }

  .importance-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #2563eb;
    cursor: pointer;
    transition: all 0.2s ease;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  }

  .importance-slider::-webkit-slider-thumb:hover {
    transform: scale(1.15);
    background: #1d4ed8;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
  }

  .importance-slider::-moz-range-thumb {
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #2563eb;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
  }

  .importance-slider::-moz-range-thumb:hover {
    transform: scale(1.15);
    background: #1d4ed8;
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
  }

  .importance-labels {
    display: flex;
    justify-content: space-between;
    font-size: 0.75rem;
    color: #6b7280;
  }

  .importance-label-min {
    color: #9ca3af;
  }

  .importance-label-default {
    color: #2563eb;
    font-weight: 500;
  }

  .importance-label-max {
    color: #059669;
  }

  .dialogue-controls {
    display: flex;
    gap: 1rem;
    margin-bottom: 2rem;
  }

  .edit-controls-left {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    flex: 1;
    min-width: 0;
  }

  .view-mode-preview-hint {
    margin: 0;
    font-size: 0.8rem;
    color: #6b7280;
    line-height: 1.4;
  }

  .edit-controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    gap: 1rem;
    flex-wrap: wrap;
  }

  .view-mode-toggle {
    display: flex;
    gap: 0.5rem;
    background-color: #f3f4f6;
    padding: 4px;
    border-radius: 8px;
  }

  .view-btn {
    background-color: transparent;
    color: #6b7280;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    transition: all 0.2s ease;
    font-size: 0.875rem;
  }

  .view-btn:hover {
    background-color: #e5e7eb;
    color: #374151;
  }

  .view-btn.active {
    background-color: #3b82f6;
    color: white;
  }

  .edit-btn {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }

  .edit-btn:hover {
    background-color: #2563eb;
  }

  .csv-download-btn,
  .csv-upload-btn {
    background-color: #059669;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }

  .csv-download-btn:hover,
  .csv-upload-btn:hover {
    background-color: #047857;
  }

  .refine-btn {
    background-color: #f59e0b;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    font-size: 1rem;
    margin-right: 1rem;
    transition: background-color 0.3s ease;
  }

  .refine-btn:hover {
    background-color: #d97706;
  }

  .edit-notice {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    background-color: #fef3c7;
    border: 1px solid #fbbf24;
    padding: 1rem;
    border-radius: 8px;
    margin: 1rem 0;
  }

  .notice-icon {
    font-size: 1.25rem;
    flex-shrink: 0;
  }

  .notice-text {
    color: #92400e;
    font-size: 0.9rem;
    line-height: 1.5;
  }

  .notice-text strong {
    font-weight: 600;
  }

  .additional-prompt-section {
    background-color: #f3f4f6;
    padding: 1.5rem;
    border-radius: 8px;
    margin-bottom: 2rem;
  }

  .additional-prompt-section label {
    display: block;
    font-weight: bold;
    margin-bottom: 0.5rem;
    color: #374151;
  }

  .additional-prompt-section textarea {
    width: 100%;
    padding: 0.75rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    resize: vertical;
    font-family: inherit;
    margin-bottom: 1rem;
  }

  .regenerate-btn {
    background-color: #8b5cf6;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }

  .regenerate-btn:hover {
    background-color: #7c3aed;
  }

  .regenerate-btn:disabled {
    background-color: #d1d5db;
    color: #9ca3af;
    cursor: not-allowed;
  }

  .regeneration-status {
    margin-top: 1rem;
    padding: 1rem;
    background-color: #f0f9ff;
    border: 1px solid #60a5fa;
    border-radius: 6px;
  }

  .status-message {
    font-size: 0.875rem;
    color: #1e40af;
    margin-bottom: 0.5rem;
  }

  .dialogue-list {
    max-height: 600px;
    overflow-y: auto;
    border: 1px solid #e5e7eb;
    border-radius: 8px;
    padding: 1rem;
    background-color: #ffffff;
  }

  .slide-dialogue {
    margin-bottom: 2rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #e5e7eb;
  }

  .slide-dialogue:last-child {
    border-bottom: none;
  }

  .slide-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
    position: relative;
  }

  .slide-thumbnail {
    width: 150px;
    height: auto;
    border-radius: 6px;
    border: 1px solid #e5e7eb;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  .slide-dialogue h4 {
    color: #1f2937;
    text-transform: capitalize;
  }

  .dialogue-item {
    display: flex;
    align-items: flex-start;
    margin-bottom: 0.75rem;
    gap: 0.75rem;
  }

  .dialogue-item-main {
    flex: 1;
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    gap: 0.5rem;
    min-width: 0;
  }

  .dialogue-item-main .dialogue-text,
  .dialogue-item-main .dialogue-text-edit {
    flex: 1 1 200px;
    min-width: 0;
  }

  .voice-preview-line-btn {
    flex-shrink: 0;
    align-self: flex-start;
    background: #7c3aed;
    color: white;
    border: none;
    padding: 0.35rem 0.65rem;
    border-radius: 6px;
    font-size: 0.8rem;
    cursor: pointer;
    white-space: nowrap;
  }

  .voice-preview-line-btn:hover:not(:disabled) {
    background: #6d28d9;
  }

  .voice-preview-line-btn:disabled {
    opacity: 0.45;
    cursor: not-allowed;
  }

  .speaker-label {
    min-width: 100px;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    font-size: 0.875rem;
    font-weight: bold;
  }

  .speaker-label.metan {
    background-color: #fef3c7;
    color: #92400e;
  }

  .speaker-label.zundamon {
    background-color: #d1fae5;
    color: #065f46;
  }

  .dialogue-text {
    flex: 1;
    padding: 0.5rem;
    background-color: #f9fafb;
    border-radius: 6px;
    line-height: 1.5;
  }

  .dialogue-text-edit {
    flex: 1;
    padding: 0.5rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    resize: vertical;
    font-family: inherit;
  }

  .remove-btn {
    background-color: #ef4444;
    color: white;
    border: none;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
  }

  .remove-btn:hover {
    background-color: #dc2626;
  }

  .add-dialogue-btn {
    background-color: #f3f4f6;
    color: #4b5563;
    border: 1px dashed #9ca3af;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    width: 100%;
    margin-top: 0.5rem;
    transition: all 0.3s ease;
  }

  .add-dialogue-btn:hover {
    background-color: #e5e7eb;
    border-color: #6b7280;
  }

  /* 会話スタイル設定 */
  .conversation-style-settings {
    margin: 2rem 0;
  }

  .conversation-style-settings h4 {
    margin-bottom: 1rem;
    color: #1f2937;
  }

  .style-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 1rem;
  }

  .style-option {
    position: relative;
  }

  .style-option input[type="radio"] {
    position: absolute;
    opacity: 0;
  }

  .style-label {
    display: flex;
    flex-direction: column;
    padding: 1rem;
    border: 2px solid #e5e7eb;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.3s ease;
    background-color: white;
  }

  .style-option input[type="radio"]:checked + .style-label {
    border-color: #3b82f6;
    background-color: #eff6ff;
  }

  .style-option input[type="radio"]:hover + .style-label {
    border-color: #93c5fd;
  }

  .style-name {
    font-weight: 600;
    font-size: 1.1rem;
    color: #1f2937;
    margin-bottom: 0.25rem;
  }

  .style-description {
    font-size: 0.875rem;
    color: #6b7280;
    line-height: 1.4;
  }

  /* 進捗セクション */
  .progress-section {
    text-align: center;
  }

  .job-info {
    background-color: #f9fafb;
    padding: 2rem;
    border-radius: 12px;
    border: 1px solid #e5e7eb;
  }

  .job-id {
    font-family: monospace;
    color: #6b7280;
    margin-bottom: 1.5rem;
  }

  .progress-bar {
    width: 100%;
    height: 1rem;
    background-color: #e5e7eb;
    border-radius: 6px;
    overflow: hidden;
    margin: 1rem 0;
  }

  .progress-fill {
    height: 100%;
    background-color: #2563eb;
    transition: width 0.3s ease;
  }

  .status-info {
    display: flex;
    justify-content: space-between;
    margin-bottom: 1rem;
    color: #374151;
  }

  .message {
    background-color: #dbeafe;
    color: #1e40af;
    padding: 0.75rem;
    border-radius: 6px;
    margin: 1rem 0;
  }

  .error {
    background-color: #fee2e2;
    color: #dc2626;
    padding: 0.75rem;
    border-radius: 6px;
    margin: 1rem 0;
  }

  .result {
    margin-top: 2rem;
  }

  .download-section {
    margin-top: 1rem;
  }

  .download-btn {
    display: inline-block;
    background-color: #10b981;
    color: white;
    text-decoration: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    margin-bottom: 1rem;
    transition: background-color 0.3s ease;
  }

  .download-btn:hover {
    background-color: #059669;
  }

  .preview-video {
    width: 100%;
    max-width: 600px;
    margin-top: 1rem;
    border-radius: 8px;
  }

  .voicevox-credit-notice {
    margin-top: 2rem;
    padding: 1.5rem;
    background-color: #fef3c7;
    border: 2px solid #f59e0b;
    border-radius: 8px;
  }

  .voicevox-credit-notice h5 {
    margin: 0 0 0.5rem 0;
    color: #d97706;
    font-size: 1.1rem;
  }

  .voicevox-credit-notice p {
    margin: 0.5rem 0;
    color: #92400e;
  }

  .credit-example {
    background-color: #fff;
    padding: 1rem;
    border-radius: 4px;
    border: 1px solid #fbbf24;
    margin: 0.5rem 0;
    font-family: monospace;
  }

  .credit-note {
    font-size: 0.9rem;
    margin-top: 0.5rem;
    color: #92400e;
  }

  .new-job-btn {
    margin-top: 2rem;
  }

  .action-buttons {
    display: flex;
    gap: 1rem;
    justify-content: center;
    margin-top: 1.5rem;
  }

  .back-to-script-btn {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    font-size: 1rem;
    transition: background-color 0.3s ease;
  }

  .back-to-script-btn:hover {
    background-color: #2563eb;
  }

  /* 目安時間設定スタイル */
  .duration-setting {
    margin: 1rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .duration-setting label {
    font-weight: 500;
    color: #374151;
  }

  .duration-setting input {
    width: 80px;
    padding: 0.5rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 1rem;
    text-align: center;
  }

  .duration-setting span {
    color: #6b7280;
  }

  /* キャラクター設定スタイル */
  .speaker-settings {
    margin: 1.5rem 0;
    padding: 1rem;
    background-color: #f9fafb;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
  }

  .speaker-settings h4 {
    margin: 0 0 1rem 0;
    color: #374151;
    font-size: 1.1rem;
  }

  .speaker-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 0.75rem;
  }

  .speaker-row:last-child {
    margin-bottom: 0;
  }

  .speaker-row label {
    min-width: 150px;
    font-weight: 500;
    color: #374151;
  }

  .speaker-row select {
    flex: 1;
    padding: 0.5rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 1rem;
    background-color: white;
    cursor: pointer;
  }

  .speaker-row select:hover {
    border-color: #9ca3af;
  }

  .speaker-row select:focus {
    outline: none;
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
  }

  .speed-row {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-top: 0.5rem;
    margin-bottom: 1rem;
    padding-left: 166px; /* label幅 + gap分のインデント */
  }

  .speed-row label {
    min-width: 150px;
    font-size: 0.9rem;
    color: #6b7280;
  }

  .speed-slider {
    flex: 1;
    height: 6px;
    background: #e5e7eb;
    border-radius: 3px;
    outline: none;
    -webkit-appearance: none;
  }

  .speed-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #2563eb;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .speed-slider::-webkit-slider-thumb:hover {
    transform: scale(1.1);
    background: #1d4ed8;
  }

  .speed-slider::-moz-range-thumb {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #2563eb;
    cursor: pointer;
    transition: all 0.2s ease;
    border: none;
  }

  .speed-slider::-moz-range-thumb:hover {
    transform: scale(1.1);
    background: #1d4ed8;
  }

  .recommendation-toggle {
    background-color: #f3f4f6;
    color: #1f2937;
    border: 1px solid #d1d5db;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    margin-bottom: 1rem;
    transition: all 0.2s ease;
    font-weight: 500;
  }

  .recommendation-toggle:hover {
    background-color: #e5e7eb;
    border-color: #9ca3af;
  }

  .recommendations {
    background-color: #f0f9ff;
    border: 1px solid #3b82f6;
    border-radius: 8px;
    padding: 1rem;
    margin-bottom: 1.5rem;
  }

  .recommendations h5 {
    margin: 0 0 1rem 0;
    color: #1e40af;
    font-size: 1rem;
  }

  .recommendation-item {
    background-color: white;
    border: 1px solid #dbeafe;
    border-radius: 6px;
    padding: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .recommendation-item:last-child {
    margin-bottom: 0;
  }

  .rec-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 0.5rem;
  }

  .rec-header strong {
    color: #1f2937;
    font-size: 0.95rem;
  }

  .apply-btn {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.25rem 0.75rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
    transition: background-color 0.2s ease;
  }

  .apply-btn:hover {
    background-color: #2563eb;
  }

  .rec-description {
    color: #6b7280;
    font-size: 0.875rem;
    margin: 0 0 0.25rem 0;
  }

  .rec-speakers {
    color: #374151;
    font-size: 0.875rem;
    margin: 0;
  }

  .sample-btn {
    background-color: #10b981;
    color: white;
    border: none;
    padding: 0.5rem;
    border-radius: 6px;
    cursor: pointer;
    font-size: 1rem;
    transition: all 0.2s ease;
    width: 40px;
    height: 40px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .sample-btn:hover {
    background-color: #059669;
    transform: scale(1.05);
  }

  .sample-btn:active {
    transform: scale(0.95);
  }

  .sample-btn:disabled {
    background-color: #9ca3af;
    cursor: not-allowed;
    transform: none;
  }

  .sample-btn.loading {
    background-color: #6b7280;
  }

  .spinner {
    display: inline-block;
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    0% {
      transform: rotate(0deg);
    }
    100% {
      transform: rotate(360deg);
    }
  }

  select:disabled,
  button:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  /* 指示履歴スタイル */
  .history-toggle {
    background-color: #e0f2fe;
    color: #0369a1;
    border: 1px solid #7dd3fc;
    padding: 0.25rem 0.75rem;
    border-radius: 6px;
    font-size: 0.875rem;
    cursor: pointer;
    transition: all 0.2s ease;
    margin-left: auto;
  }

  .history-toggle:hover {
    background-color: #bae6fd;
    border-color: #38bdf8;
  }

  .instruction-history {
    background-color: #f0f9ff;
    border: 1px solid #bae6fd;
    border-radius: 8px;
    padding: 1rem;
    margin: 1rem 0;
  }

  .instruction-history h5 {
    margin: 0 0 0.75rem 0;
    color: #0369a1;
    font-size: 0.9rem;
    font-weight: 600;
  }

  .history-item {
    background-color: white;
    border: 1px solid #e0e7ff;
    border-radius: 6px;
    padding: 0.75rem;
    margin-bottom: 0.5rem;
  }

  .history-item:last-child {
    margin-bottom: 0;
  }

  .history-timestamp {
    font-size: 0.75rem;
    color: #6b7280;
    margin-bottom: 0.25rem;
  }

  .history-instruction {
    color: #1f2937;
    font-size: 0.875rem;
    line-height: 1.5;
  }

  /* 画像クリック可能スタイル */
  .slide-thumbnail.clickable {
    cursor: pointer;
    transition: transform 0.2s ease;
  }

  .slide-thumbnail.clickable:hover {
    transform: scale(1.05);
    box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
  }

  /* モーダルスタイル */
  .modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-color: rgba(0, 0, 0, 0.8);
    display: flex;
    justify-content: center;
    align-items: center;
    z-index: 1000;
    cursor: pointer;
  }

  .modal-content {
    position: relative;
    max-width: 90vw;
    max-height: 90vh;
    background-color: white;
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    cursor: default;
  }

  .modal-image {
    max-width: 100%;
    max-height: 90vh;
    border-radius: 8px;
    display: block;
  }

  .modal-close {
    position: absolute;
    top: -40px;
    right: 0;
    background-color: white;
    border: none;
    border-radius: 50%;
    width: 36px;
    height: 36px;
    font-size: 20px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
  }

  .modal-close:hover {
    background-color: #f3f4f6;
    transform: scale(1.1);
  }

  /* APIキー警告ポップアップ */
  .api-key-warning {
    background-color: white;
    border-radius: 12px;
    padding: 2rem;
    max-width: 500px;
    box-shadow:
      0 20px 25px -5px rgba(0, 0, 0, 0.1),
      0 10px 10px -5px rgba(0, 0, 0, 0.04);
    animation: slideUp 0.3s ease-out;
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .api-key-warning h2 {
    font-size: 1.5rem;
    margin-bottom: 1rem;
    color: #dc2626;
  }

  .api-key-warning p {
    margin-bottom: 1.5rem;
    color: #4b5563;
    line-height: 1.6;
  }

  .warning-actions {
    display: flex;
    gap: 1rem;
    justify-content: center;
  }

  .warning-actions .primary-btn {
    background-color: #2563eb;
    color: white;
    padding: 0.75rem 2rem;
    border-radius: 8px;
    text-decoration: none;
    font-weight: 500;
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    transition: background-color 0.3s ease;
  }

  .warning-actions .primary-btn:hover {
    background-color: #1d4ed8;
  }

  .warning-actions .secondary-btn {
    background-color: #e5e7eb;
    color: #4b5563;
    padding: 0.75rem 2rem;
    border-radius: 8px;
    border: none;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }

  .warning-actions .secondary-btn:hover {
    background-color: #d1d5db;
  }

  .back-to-settings-btn {
    background-color: #6b7280;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    font-size: 1rem;
    transition: background-color 0.3s ease;
  }

  .back-to-settings-btn:hover {
    background-color: #4b5563;
  }

  .dialogue-controls {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    margin-bottom: 2rem;
    align-items: center;
  }

  .edit-btn {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }

  .edit-btn:hover {
    background-color: #2563eb;
  }

  .csv-download-btn,
  .csv-upload-btn {
    background-color: #059669;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }

  .csv-download-btn:hover,
  .csv-upload-btn:hover {
    background-color: #047857;
  }

  .back-to-dialogue-btn {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.3s ease;
  }

  .back-to-dialogue-btn:hover {
    background-color: #2563eb;
  }

  /* ナレッジセクションのスタイル */
  .knowledge-section {
    margin: 1.5rem 0;
    padding: 1rem;
    background-color: #f9fafb;
    border-radius: 8px;
    border: 1px solid #e5e7eb;
  }

  .knowledge-toggle {
    background-color: transparent;
    border: none;
    padding: 0.5rem;
    cursor: pointer;
    font-size: 1rem;
    font-weight: 500;
    color: #374151;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    transition: color 0.2s ease;
    width: 100%;
    text-align: left;
  }

  .knowledge-toggle:hover {
    color: #1f2937;
  }

  .toggle-icon {
    font-size: 0.75rem;
    transition: transform 0.2s ease;
  }

  .knowledge-content {
    margin-top: 1rem;
    animation: slideDown 0.3s ease-out;
  }

  @keyframes slideDown {
    from {
      opacity: 0;
      transform: translateY(-10px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .knowledge-description {
    font-size: 0.875rem;
    color: #6b7280;
    margin-bottom: 1rem;
    line-height: 1.5;
  }

  .knowledge-description strong {
    color: #374151;
    font-weight: 600;
  }

  .knowledge-supported-formats {
    font-size: 0.85rem;
    color: #4b5563;
    margin-bottom: 1rem;
    padding: 0.5rem;
    background-color: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 4px;
  }

  .knowledge-upload-area {
    margin-top: 1rem;
  }

  .knowledge-dropzone {
    border: 2px dashed #d1d5db;
    border-radius: 8px;
    padding: 2rem;
    text-align: center;
    background-color: #f9fafb;
    transition: all 0.3s ease;
  }

  .knowledge-dropzone:hover {
    border-color: #3b82f6;
    background-color: #f0f9ff;
  }

  .knowledge-upload-icon {
    font-size: 2rem;
    margin-bottom: 0.5rem;
  }

  .knowledge-file-input {
    display: none;
  }

  .knowledge-file-label {
    display: inline-block;
    background-color: #3b82f6;
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    cursor: pointer;
    transition: background-color 0.3s ease;
    margin-top: 0.5rem;
  }

  .knowledge-file-label:hover {
    background-color: #2563eb;
  }

  .knowledge-file-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem;
    background-color: #f0f9ff;
    border: 1px solid #3b82f6;
    border-radius: 6px;
  }

  .knowledge-file-name {
    font-weight: 500;
    color: #1e40af;
    flex: 1;
  }

  .knowledge-file-size {
    font-size: 0.85rem;
    color: #6b7280;
  }

  .knowledge-remove-btn {
    background-color: #ef4444;
    color: white;
    border: none;
    padding: 0.25rem 0.5rem;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.875rem;
    transition: background-color 0.3s ease;
  }

  .knowledge-remove-btn:hover {
    background-color: #dc2626;
  }

  /* Hero Section - Enhanced Minimalist */
  .hero-section {
    background: linear-gradient(to bottom, #ffffff 0%, #fafafa 100%);
    padding: 10rem 2rem 8rem;
    min-height: 85vh;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    overflow: hidden;
  }

  .hero-section::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(to right, transparent, #e0e0e0, transparent);
  }

  .hero-container {
    max-width: 1200px;
    width: 100%;
    margin: 0 auto;
    position: relative;
    z-index: 1;
  }

  .hero-main {
    text-align: left;
    max-width: 720px;
    animation: fadeInUp 0.8s ease-out;
  }

  @keyframes fadeInUp {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .hero-title {
    font-size: 7rem;
    font-weight: 800;
    margin: 0 0 1.5rem 0;
    letter-spacing: -0.08em;
    line-height: 1;
    position: relative;
    display: inline-block;
    background: linear-gradient(135deg, #0a0a0a 0%, #2a2a2a 50%, #0a0a0a 100%);
    background-size: 200% 200%;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    animation: titleGradient 3s ease infinite, titleFadeIn 0.8s ease-out;
  }

  @keyframes titleGradient {
    0%, 100% {
      background-position: 0% 50%;
    }
    50% {
      background-position: 100% 50%;
    }
  }

  @keyframes titleFadeIn {
    from {
      opacity: 0;
      transform: translateY(20px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .hero-title ruby {
    position: relative;
  }

  .hero-title rt {
    font-size: 1.5rem;
    font-weight: 500;
    color: #999;
    display: block;
    margin-top: 0.75rem;
    letter-spacing: 0.05em;
    opacity: 0;
    animation: rubyFadeIn 0.8s ease-out 0.4s forwards;
  }

  @keyframes rubyFadeIn {
    from {
      opacity: 0;
      transform: translateY(8px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  .hero-tagline {
    font-size: 1.625rem;
    color: #4a4a4a;
    margin: 0 0 2.5rem 0;
    font-weight: 400;
    letter-spacing: -0.02em;
    line-height: 1.5;
  }

  .hero-description {
    font-size: 1.125rem;
    line-height: 1.75;
    color: #666;
    margin: 0 0 3.5rem 0;
    max-width: 640px;
    font-weight: 400;
  }

  .hero-cta {
    display: flex;
    gap: 1rem;
    align-items: center;
    flex-wrap: wrap;
    margin-bottom: 4rem;
  }

  .cta-primary {
    background: #0a0a0a;
    color: #ffffff;
    padding: 1.125rem 2.25rem;
    border-radius: 10px;
    font-weight: 500;
    font-size: 1rem;
    border: none;
    cursor: pointer;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    letter-spacing: -0.01em;
    position: relative;
    overflow: hidden;
  }

  .cta-primary::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
    transition: left 0.5s ease;
  }

  .cta-primary:hover::before {
    left: 100%;
  }

  .cta-primary:hover {
    background: #1a1a1a;
    transform: translateY(-2px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  }

  .cta-primary:active {
    transform: translateY(0);
  }

  .cta-secondary {
    color: #0a0a0a;
    padding: 1.125rem 2.25rem;
    border-radius: 10px;
    font-weight: 500;
    font-size: 1rem;
    text-decoration: none;
    border: 1.5px solid #d0d0d0;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    letter-spacing: -0.01em;
    background: #ffffff;
  }

  .cta-secondary:hover {
    border-color: #0a0a0a;
    background: #fafafa;
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  }

  .hero-features-minimal {
    display: flex;
    gap: 0.75rem;
    margin-top: 5rem;
    flex-wrap: wrap;
    padding-top: 3rem;
    border-top: 1px solid #e8e8e8;
  }

  .feature-badge {
    padding: 0.625rem 1.25rem;
    background: #f5f5f5;
    border-radius: 24px;
    font-size: 0.875rem;
    color: #4a4a4a;
    font-weight: 400;
    border: 1px solid #e8e8e8;
    transition: all 0.2s ease;
  }

  .feature-badge:hover {
    background: #eeeeee;
    border-color: #d0d0d0;
    transform: translateY(-1px);
  }

  /* Features Grid Section - Enhanced */
  .features-grid-section {
    padding: 10rem 2rem;
    background: #ffffff;
    position: relative;
  }

  .features-grid-section::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(to right, transparent, #e0e0e0, transparent);
  }

  .features-container {
    max-width: 1200px;
    margin: 0 auto;
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 5rem 4rem;
  }

  .feature-box {
    text-align: left;
    position: relative;
    padding: 2rem 0;
    transition: all 0.3s ease;
  }

  .feature-box::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    width: 2px;
    height: 0;
    background: linear-gradient(to bottom, #0a0a0a, transparent);
    transition: height 0.4s ease;
  }

  .feature-box:hover::before {
    height: 100%;
  }

  .feature-box:hover {
    transform: translateX(8px);
  }

  .feature-number {
    font-size: 0.875rem;
    font-weight: 600;
    color: #999;
    margin-bottom: 1.5rem;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    font-family: 'SF Mono', 'Monaco', 'Consolas', monospace;
  }

  .feature-title {
    font-size: 1.75rem;
    font-weight: 600;
    color: #0a0a0a;
    margin: 0 0 1.25rem 0;
    letter-spacing: -0.03em;
    line-height: 1.3;
  }

  .feature-text {
    font-size: 1.0625rem;
    line-height: 1.75;
    color: #666;
    margin: 0;
    font-weight: 400;
  }

  /* Benefits Section - Enhanced */
  .benefits-section {
    padding: 10rem 2rem;
    background: linear-gradient(to bottom, #fafafa 0%, #ffffff 100%);
    position: relative;
  }

  .benefits-section::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 1px;
    background: linear-gradient(to right, transparent, #e0e0e0, transparent);
  }

  .benefits-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 2rem;
  }

  .benefits-content {
    text-align: left;
    max-width: 800px;
    margin: 0 auto;
  }

  .benefits-title {
    font-size: 3.5rem;
    font-weight: 700;
    color: #0a0a0a;
    margin: 0 0 1.5rem 0;
    letter-spacing: -0.04em;
    line-height: 1.1;
    position: relative;
    padding-bottom: 1.5rem;
  }

  .benefits-title::after {
    content: '';
    position: absolute;
    bottom: 0;
    left: 0;
    width: 60px;
    height: 3px;
    background: #0a0a0a;
    border-radius: 2px;
  }

  .benefits-subtitle {
    font-size: 1.375rem;
    color: #666;
    margin: 0 0 5rem 0;
    line-height: 1.7;
    font-weight: 400;
    letter-spacing: -0.01em;
    max-width: 700px;
  }

  .benefits-list {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 2rem;
    margin-bottom: 5rem;
  }

  .benefit-item {
    display: flex;
    gap: 1.5rem;
    align-items: flex-start;
    padding: 2rem;
    border-radius: 16px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    background: #ffffff;
    border: 1px solid #e8e8e8;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  }

  .benefit-item::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    background: linear-gradient(to bottom, #0a0a0a, #2a2a2a);
    border-radius: 0 2px 2px 0;
    transform: scaleX(0);
    transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    transform-origin: left;
  }

  .benefit-item:hover::before {
    transform: scaleX(1);
  }

  .benefit-item:hover {
    background: #fafafa;
    border-color: #d0d0d0;
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  }

  .benefit-icon {
    width: 32px;
    height: 32px;
    border-radius: 50%;
    background: linear-gradient(135deg, #0a0a0a 0%, #2a2a2a 100%);
    color: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    font-weight: 600;
    flex-shrink: 0;
    margin-top: 2px;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  }

  .benefit-item:hover .benefit-icon {
    transform: scale(1.1) rotate(5deg);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }

  .benefit-text {
    flex: 1;
    padding-top: 2px;
  }

  .benefit-text strong {
    display: block;
    font-size: 1.375rem;
    font-weight: 600;
    color: #0a0a0a;
    margin-bottom: 0.75rem;
    letter-spacing: -0.02em;
    line-height: 1.3;
  }

  .benefit-text span {
    display: block;
    font-size: 1rem;
    color: #666;
    line-height: 1.7;
    font-weight: 400;
  }

  .benefits-note {
    font-size: 0.875rem;
    color: #999;
    line-height: 1.8;
    padding: 2rem;
    background: #f9f9f9;
    border-radius: 12px;
    border: 1px solid #e8e8e8;
    margin-top: 3rem;
  }

  /* Features Section - Bright */
  .features-section {
    padding: 8rem 2rem;
    background: #ffffff;
    position: relative;
  }

  .features-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    gap: 1.5rem;
    max-width: 1200px;
    margin: 0 auto 2rem;
  }

  .feature-card {
    background: rgba(255, 255, 255, 0.03);
    backdrop-filter: blur(10px);
    padding: 2.5rem;
    border-radius: 20px;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.1);
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
  }

  .feature-card::after {
    content: '';
    position: absolute;
    top: -50%;
    left: -50%;
    width: 200%;
    height: 200%;
    background: radial-gradient(circle, rgba(99, 102, 241, 0.1) 0%, transparent 70%);
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .feature-card:hover::after {
    opacity: 1;
  }

  .feature-card:hover {
    box-shadow: 0 12px 48px rgba(99, 102, 241, 0.4);
    transform: translateY(-8px) scale(1.03);
    border-color: rgba(99, 102, 241, 0.5);
    background: rgba(99, 102, 241, 0.05);
  }

  .feature-card-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
  }

  .feature-card-icon {
    font-size: 2rem;
    transition: transform 0.2s ease;
  }

  .feature-card:hover .feature-card-icon {
    transform: scale(1.05);
  }

  .feature-card h3 {
    font-size: 1.375rem;
    font-weight: 600;
    color: #ffffff;
    margin: 0;
    position: relative;
    z-index: 1;
  }

  .feature-card p {
    color: #c7d2fe;
    font-weight: 400;
    line-height: 1.7;
    font-size: 1rem;
    position: relative;
    z-index: 1;
  }

  .features-note {
    text-align: center;
    color: #6b7280;
    font-size: 0.95rem;
    max-width: 900px;
    margin: 3rem auto 0;
    line-height: 1.8;
    padding: 2rem;
    background: #f9fafb;
    border-radius: 16px;
    border: 1px solid #e5e7eb;
  }

  /* How It Works Section - Bright */
  .how-it-works-section {
    padding: 8rem 2rem;
    background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
  }

  .workflow {
    max-width: 1000px;
    margin: 0 auto;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 1.5rem;
  }

  .workflow-step {
    background: #ffffff;
    padding: 3rem;
    border-radius: 20px;
    text-align: center;
    width: 100%;
    max-width: 650px;
    border: 1px solid #e5e7eb;
    transition: all 0.3s ease;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    position: relative;
    overflow: hidden;
  }

  .workflow-step::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #667eea, #764ba2, #f093fb);
    transform: scaleX(0);
    transition: transform 0.3s ease;
  }

  .workflow-step:hover::before {
    transform: scaleX(1);
  }

  .workflow-step:hover {
    border-color: #c7d2fe;
    box-shadow: 0 12px 40px rgba(102, 126, 234, 0.2);
    transform: translateY(-8px) scale(1.02);
  }

  .workflow-step h3 {
    font-size: 1.5rem;
    font-weight: 600;
    color: #1f2937;
    margin-bottom: 1rem;
  }

  .workflow-step p {
    color: #4b5563;
    line-height: 1.7;
    font-size: 1rem;
  }

  .workflow-step ul {
    text-align: left;
    color: #4b5563;
    line-height: 1.9;
    margin-top: 1.5rem;
    list-style: none;
    padding: 0;
  }

  .workflow-step li {
    margin-bottom: 0.75rem;
    padding-left: 1.5rem;
    position: relative;
  }

  .workflow-step li::before {
    content: '✓';
    position: absolute;
    left: 0;
    color: #667eea;
    font-weight: bold;
    font-size: 1.2rem;
  }

  .workflow-arrow {
    font-size: 2.5rem;
    background: linear-gradient(135deg, #667eea, #764ba2);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-weight: bold;
    opacity: 0.8;
    transition: all 0.3s ease;
    animation: arrowPulse 2s ease-in-out infinite;
  }

  @keyframes arrowPulse {
    0%, 100% {
      opacity: 0.6;
      transform: translateY(0);
    }
    50% {
      opacity: 1;
      transform: translateY(5px);
    }
  }

  .workflow-arrow:hover {
    opacity: 1;
    transform: translateY(10px) scale(1.2);
  }

  .header-actions {
    display: flex;
    gap: 1rem;
    align-items: center;
  }

  .skip-intro-btn {
    background-color: #6b7280;
    color: white;
    padding: 0.5rem 1rem;
    border-radius: 6px;
    border: none;
    cursor: pointer;
    font-size: 0.9rem;
    transition: background-color 0.3s ease;
  }

  .skip-intro-btn:hover {
    background-color: #4b5563;
  }

  @media (max-width: 768px) {
    .hero-section {
      padding: 8rem 1.5rem 4rem;
      min-height: auto;
    }

    .hero-title {
      font-size: 3.5rem;
    }

    .hero-title rt {
      font-size: 1.125rem;
      margin-top: 0.5rem;
    }

    .hero-tagline {
      font-size: 1.25rem;
    }

    .hero-description {
      font-size: 1rem;
    }

    .features-container {
      grid-template-columns: 1fr;
      gap: 3rem;
    }

    .benefits-list {
      grid-template-columns: 1fr;
      gap: 1.5rem;
    }

    .benefit-item {
      padding: 1.5rem;
    }

    .benefits-title {
      font-size: 2.5rem;
    }

    .benefits-title::after {
      width: 40px;
    }

    .benefits-subtitle {
      font-size: 1.125rem;
      margin-bottom: 3rem;
    }

    .benefit-text strong {
      font-size: 1.125rem;
    }

    .benefit-text span {
      font-size: 0.9375rem;
    }
  }

  /* 動画設定パネル */
  .settings-toggle-btn {
    background-color: #6b7280;
    color: white;
    padding: 0.75rem 1.5rem;
    border-radius: 8px;
    border: none;
    cursor: pointer;
    font-size: 0.9rem;
    transition: background-color 0.3s ease;
    margin-right: 0.5rem;
  }

  .settings-toggle-btn:hover {
    background-color: #4b5563;
  }

  .video-settings-panel {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 1.5rem;
    margin-top: 1rem;
    margin-bottom: 1rem;
  }

  .video-settings-panel h4 {
    margin-top: 0;
    margin-bottom: 1.5rem;
    color: #1f2937;
    font-size: 1.25rem;
  }

  .setting-group {
    margin-bottom: 1.5rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid #e5e7eb;
  }

  .setting-group:last-child {
    border-bottom: none;
    margin-bottom: 0;
    padding-bottom: 0;
  }

  .checkbox-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    cursor: pointer;
    font-weight: 500;
    color: #374151;
    margin-bottom: 1rem;
  }

  .checkbox-label input[type="checkbox"] {
    width: 18px;
    height: 18px;
    cursor: pointer;
  }

  .setting-subgroup {
    margin-left: 1.5rem;
    margin-top: 1rem;
  }

  .setting-subgroup label {
    display: block;
    margin-bottom: 0.5rem;
    color: #4b5563;
    font-size: 0.9rem;
  }

  .setting-input {
    width: 100%;
    max-width: 400px;
    padding: 0.5rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.9rem;
    margin-bottom: 0.5rem;
  }

  .setting-hint {
    display: block;
    color: #6b7280;
    font-size: 0.85rem;
    margin-top: 0.25rem;
    margin-bottom: 1rem;
  }

  .setting-slider {
    width: 100%;
    max-width: 400px;
    margin-bottom: 0.5rem;
  }

  .setting-select {
    width: 100%;
    max-width: 400px;
    padding: 0.5rem;
    border: 1px solid #d1d5db;
    border-radius: 6px;
    font-size: 0.9rem;
    margin-bottom: 1rem;
    background-color: white;
    cursor: pointer;
  }
</style>
