<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';

	interface Job {
		job_id: string;
		status: string;
		status_code: string;
		created_at: string;
		updated_at: string;
		progress: number;
		result_url?: string;
		error_code?: string | null;
		estimated_duration?: number | null;
		target_duration?: number | null;
		metadata?: { original_pdf_filename?: string; [key: string]: unknown };
	}

	let jobs: Job[] = [];
	let isLoading = true;
	let error: string | null = null;
	let deletingJobId: string | null = null;
	let searchText = '';
	let statusFilter = ''; // '' = すべて, completed, failed, processing, pending

	// 検索・フィルタ適用後の一覧（クライアント側）
	$: filteredJobs = jobs.filter((job) => {
		const matchStatus = !statusFilter || job.status === statusFilter;
		if (!matchStatus) return false;
		if (!searchText.trim()) return true;
		const q = searchText.trim().toLowerCase();
		const filename = (job.metadata?.original_pdf_filename ?? '').toLowerCase();
		const id = job.job_id.toLowerCase();
		return filename.includes(q) || id.includes(q);
	});

	onMount(async () => {
		await loadJobs();
	});

	async function loadJobs() {
		isLoading = true;
		error = null;
		try {
			const response = await fetch('/api/jobs');
			if (response.ok) {
				jobs = await response.json();
				// 作成日時でソート（新しい順）
				jobs.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
			} else {
				error = 'ジョブリストの取得に失敗しました';
			}
		} catch (err) {
			error = 'ジョブリストの読み込み中にエラーが発生しました';
			console.error(err);
		} finally {
			isLoading = false;
		}
	}

	async function deleteJob(jobId: string) {
		if (!confirm('このジョブを削除してもよろしいですか？\n\n削除すると、このジョブのデータと生成された動画は復元できません。')) {
			return;
		}

		deletingJobId = jobId;
		try {
			const response = await fetch(`/api/jobs/${jobId}`, {
				method: 'DELETE'
			});

			if (response.ok) {
				// リストから削除
				jobs = jobs.filter(job => job.job_id !== jobId);
			} else {
				alert('ジョブの削除に失敗しました');
			}
		} catch (err) {
			alert('ジョブの削除中にエラーが発生しました');
			console.error(err);
		} finally {
			deletingJobId = null;
		}
	}

	function formatDate(dateString: string): string {
		const date = new Date(dateString);
		return date.toLocaleString('ja-JP', {
			year: 'numeric',
			month: '2-digit',
			day: '2-digit',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function getStatusBadgeClass(status: string): string {
		switch (status) {
			case 'completed':
				return 'status-completed';
			case 'processing':
				return 'status-processing';
			case 'failed':
				return 'status-failed';
			case 'pending':
				return 'status-pending';
			default:
				return 'status-unknown';
		}
	}

	function getStatusText(status: string, statusCode: string): string {
		const statusMap: { [key: string]: string } = {
			'completed': '完了',
			'processing': '処理中',
			'failed': '失敗',
			'pending': '待機中',
			'COMPLETED': '完了',
			'PROCESSING': '処理中',
			'FAILED': '失敗',
			'PENDING': '待機中',
			'PDF_PROCESSING': 'PDF処理中',
			'DIALOGUE_GENERATING': '対話生成中',
			'AUDIO_GENERATING': '音声生成中',
			'VIDEO_CREATING': '動画作成中',
			'VIDEO_ENCODING': '動画エンコーディング中'
		};
		return statusMap[statusCode] || statusMap[status] || status;
	}

	function downloadVideo(jobId: string) {
		window.open(`/api/jobs/${jobId}/download`, '_blank');
	}

	function viewJob(jobId: string) {
		// メインページに戻って、このジョブを読み込む
		goto(`/?job_id=${jobId}`);
	}
</script>

<div class="container">
	<div class="header">
		<button
			on:click={() => goto('/')}
			class="back-button"
		>
			← 戻る
		</button>
		<h1>📋 ジョブ履歴</h1>
		<div style="width: 100px;"></div>
	</div>

	<div class="filters">
		<div class="filter-row">
			<input
				type="text"
				bind:value={searchText}
				placeholder="PDFファイル名またはジョブIDで検索..."
				class="search-input"
			/>
			<select bind:value={statusFilter} class="status-select">
				<option value="">すべてのステータス</option>
				<option value="completed">完了</option>
				<option value="processing">処理中</option>
				<option value="pending">待機中</option>
				<option value="failed">失敗</option>
			</select>
			<button
				on:click={loadJobs}
				class="refresh-button"
				disabled={isLoading}
			>
				🔄 更新
			</button>
		</div>
	</div>

	{#if isLoading}
		<div class="loading-container">
			<div class="spinner"></div>
			<p>読み込み中...</p>
		</div>
	{:else if error}
		<div class="error-container">
			<p>❌ {error}</p>
			<button on:click={loadJobs} class="retry-button">再試行</button>
		</div>
	{:else if jobs.length === 0}
		<div class="empty-container">
			<p>📭 ジョブ履歴がありません</p>
			<p class="empty-hint">PDFをアップロードして動画を生成すると、ここに履歴が表示されます。</p>
		</div>
	{:else if filteredJobs.length === 0}
		<div class="empty-container">
			<p>🔍 検索条件に一致するジョブがありません</p>
			<p class="empty-hint">検索ワードまたはステータスフィルタを変えてください。</p>
		</div>
	{:else}
		<div class="jobs-list">
			<div class="jobs-header">
				<span class="jobs-count">
					{filteredJobs.length} 件を表示
					{#if jobs.length !== filteredJobs.length}
						（全 {jobs.length} 件中）
					{/if}
				</span>
			</div>

			{#each filteredJobs as job (job.job_id)}
				<div class="job-card">
					<div class="job-header">
						<div class="job-info">
							{#if job.metadata?.original_pdf_filename}
								<div class="job-filename" title={job.metadata.original_pdf_filename}>
									📄 {job.metadata.original_pdf_filename}
								</div>
							{/if}
							<div class="job-id">
								<strong>ジョブID:</strong> 
								<span class="job-id-value">{job.job_id.substring(0, 8)}...</span>
							</div>
							<div class="job-status">
								<span class="status-badge {getStatusBadgeClass(job.status)}">
									{getStatusText(job.status, job.status_code)}
								</span>
								{#if job.status === 'processing'}
									<span class="progress-text">{job.progress}%</span>
								{/if}
							</div>
						</div>
						<div class="job-actions">
							{#if job.status === 'completed' && job.result_url}
								<button
									on:click={() => downloadVideo(job.job_id)}
									class="action-button download-button"
									title="動画をダウンロード"
								>
									⬇️ ダウンロード
								</button>
							{/if}
							<button
								on:click={() => viewJob(job.job_id)}
								class="action-button view-button"
								title="編集画面で開く"
							>
								✏️ 再編集
							</button>
							<button
								on:click={() => deleteJob(job.job_id)}
								class="action-button delete-button"
								disabled={deletingJobId === job.job_id}
								title="ジョブを削除"
							>
								{deletingJobId === job.job_id ? '⏳ 削除中...' : '🗑️ 削除'}
							</button>
						</div>
					</div>

					<div class="job-details">
						<div class="detail-row">
							<span class="detail-label">作成日時:</span>
							<span class="detail-value">{formatDate(job.created_at)}</span>
						</div>
						<div class="detail-row">
							<span class="detail-label">更新日時:</span>
							<span class="detail-value">{formatDate(job.updated_at)}</span>
						</div>
						{#if job.target_duration}
							<div class="detail-row">
								<span class="detail-label">目標時間:</span>
								<span class="detail-value">{job.target_duration} 分</span>
							</div>
						{/if}
						{#if job.estimated_duration}
							<div class="detail-row">
								<span class="detail-label">推定時間:</span>
								<span class="detail-value">{Math.round(job.estimated_duration / 60)} 分 {job.estimated_duration % 60} 秒</span>
							</div>
						{/if}
						{#if job.error_code}
							<div class="detail-row error-row">
								<span class="detail-label">エラー:</span>
								<span class="detail-value error-value">{job.error_code}</span>
							</div>
						{/if}
					</div>

					{#if job.status === 'processing'}
						<div class="progress-bar-container">
							<div class="progress-bar" style="width: {job.progress}%"></div>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.container {
		max-width: 1200px;
		margin: 0 auto;
		padding: 2rem;
		font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
	}

	.header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 2rem;
	}

	.back-button {
		background-color: #6b7280;
		color: white;
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 8px;
		cursor: pointer;
		font-size: 0.9rem;
		transition: background-color 0.3s ease;
	}

	.back-button:hover {
		background-color: #4b5563;
	}

	h1 {
		font-size: 2rem;
		color: #1f2937;
		margin: 0;
	}

	.filters {
		margin-bottom: 1.5rem;
	}

	.filter-row {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: center;
	}

	.search-input {
		flex: 1;
		min-width: 200px;
		padding: 0.5rem 0.75rem;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		font-size: 0.9rem;
	}

	.search-input:focus {
		outline: none;
		border-color: #3b82f6;
		box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2);
	}

	.status-select {
		padding: 0.5rem 0.75rem;
		border: 1px solid #e5e7eb;
		border-radius: 8px;
		font-size: 0.9rem;
		background: white;
	}

	.job-filename {
		font-size: 0.95rem;
		color: #1f2937;
		margin-bottom: 0.35rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.refresh-button {
		background-color: #3b82f6;
		color: white;
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 8px;
		cursor: pointer;
		font-size: 0.9rem;
		transition: background-color 0.3s ease;
	}

	.refresh-button:hover:not(:disabled) {
		background-color: #2563eb;
	}

	.refresh-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.loading-container,
	.error-container,
	.empty-container {
		text-align: center;
		padding: 3rem;
		background-color: #f9fafb;
		border-radius: 12px;
	}

	.spinner {
		border: 4px solid #f3f4f6;
		border-top: 4px solid #3b82f6;
		border-radius: 50%;
		width: 40px;
		height: 40px;
		animation: spin 1s linear infinite;
		margin: 0 auto 1rem;
	}

	@keyframes spin {
		0% { transform: rotate(0deg); }
		100% { transform: rotate(360deg); }
	}

	.error-container {
		color: #dc2626;
	}

	.retry-button {
		margin-top: 1rem;
		background-color: #dc2626;
		color: white;
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 8px;
		cursor: pointer;
	}

	.empty-container {
		color: #6b7280;
	}

	.empty-hint {
		font-size: 0.9rem;
		margin-top: 0.5rem;
	}

	.jobs-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.jobs-header {
		padding: 0.75rem 1rem;
		background-color: #f3f4f6;
		border-radius: 8px;
		margin-bottom: 0.5rem;
	}

	.jobs-count {
		font-weight: 600;
		color: #374151;
	}

	.job-card {
		background-color: white;
		border: 1px solid #e5e7eb;
		border-radius: 12px;
		padding: 1.5rem;
		transition: box-shadow 0.3s ease;
	}

	.job-card:hover {
		box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
	}

	.job-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		margin-bottom: 1rem;
		gap: 1rem;
	}

	.job-info {
		flex: 1;
	}

	.job-id {
		font-size: 0.9rem;
		color: #6b7280;
		margin-bottom: 0.5rem;
	}

	.job-id-value {
		font-family: monospace;
		color: #374151;
	}

	.job-status {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.status-badge {
		padding: 0.25rem 0.75rem;
		border-radius: 6px;
		font-size: 0.875rem;
		font-weight: 600;
	}

	.status-completed {
		background-color: #d1fae5;
		color: #065f46;
	}

	.status-processing {
		background-color: #dbeafe;
		color: #1e40af;
	}

	.status-failed {
		background-color: #fee2e2;
		color: #991b1b;
	}

	.status-pending {
		background-color: #f3f4f6;
		color: #374151;
	}

	.status-unknown {
		background-color: #f9fafb;
		color: #6b7280;
	}

	.progress-text {
		font-size: 0.875rem;
		color: #1e40af;
		font-weight: 600;
	}

	.job-actions {
		display: flex;
		gap: 0.5rem;
		flex-shrink: 0;
	}

	.action-button {
		border: none;
		padding: 0.5rem 1rem;
		border-radius: 6px;
		cursor: pointer;
		font-size: 0.875rem;
		transition: all 0.3s ease;
		white-space: nowrap;
	}

	.download-button {
		background-color: #10b981;
		color: white;
	}

	.download-button:hover {
		background-color: #059669;
	}

	.view-button {
		background-color: #3b82f6;
		color: white;
	}

	.view-button:hover {
		background-color: #2563eb;
	}

	.delete-button {
		background-color: #ef4444;
		color: white;
	}

	.delete-button:hover:not(:disabled) {
		background-color: #dc2626;
	}

	.delete-button:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.job-details {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: 0.75rem;
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid #e5e7eb;
	}

	.detail-row {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.detail-label {
		font-size: 0.75rem;
		color: #6b7280;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.detail-value {
		font-size: 0.9rem;
		color: #1f2937;
	}

	.error-row {
		grid-column: 1 / -1;
	}

	.error-value {
		color: #dc2626;
	}

	.progress-bar-container {
		margin-top: 1rem;
		height: 8px;
		background-color: #e5e7eb;
		border-radius: 4px;
		overflow: hidden;
	}

	.progress-bar {
		height: 100%;
		background-color: #3b82f6;
		transition: width 0.3s ease;
	}

	@media (max-width: 768px) {
		.container {
			padding: 1rem;
		}

		.job-header {
			flex-direction: column;
		}

		.job-actions {
			width: 100%;
			justify-content: flex-end;
		}

		.job-details {
			grid-template-columns: 1fr;
		}
	}
</style>




