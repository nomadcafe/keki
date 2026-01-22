import type { Handle } from '@sveltejs/kit';

// Docker環境では内部ネットワークを使用
const API_URL = process.env.INTERNAL_API_URL || 'http://api:8000';

// SvelteKitのデフォルトのbody size limitを回避するため、
// file uploadは直接fetchを使用
export const handle: Handle = async ({ event, resolve }) => {
    // APIリクエストをプロキシ
    if (event.url.pathname.startsWith('/api')) {
        const apiUrl = `${API_URL}${event.url.pathname}`;
        
        console.log(`Proxying request to: ${apiUrl}`);
        
        try {
            // multipart/form-dataの場合は特別な処理
            const contentType = event.request.headers.get('content-type') || '';
            console.log(`Content-Type: ${contentType}`);
            console.log(`Content-Length: ${event.request.headers.get('content-length')}`);
            
            let body;
            if (contentType.includes('multipart/form-data')) {
                // multipart/form-dataの場合はそのまま転送
                console.log('Processing multipart/form-data...');
                body = event.request.body;
            } else {
                // その他の場合は通常通り
                console.log('Processing regular request...');
                body = await event.request.arrayBuffer();
            }
            
            // リクエストヘッダーをコピー（Host以外）
            const headers = new Headers();
            event.request.headers.forEach((value, key) => {
                if (key.toLowerCase() !== 'host' && key.toLowerCase() !== 'connection') {
                    headers.set(key, value);
                }
            });
            
            console.log(`Sending ${event.request.method} request to ${apiUrl}...`);
            
            // 状態チェックリクエストには適切なタイムアウトを設定
            const isStatusCheck = event.url.pathname.includes('/status');
            const timeout = isStatusCheck ? 10000 : 300000; // 状態チェック: 10秒、その他: 5分
            
            // 状態チェックリクエストにはリトライロジックを追加
            let lastError: Error | null = null;
            const maxRetries = isStatusCheck ? 3 : 1;
            
            for (let attempt = 0; attempt < maxRetries; attempt++) {
                try {
                    const response = await fetch(apiUrl, {
                        method: event.request.method,
                        headers: headers,
                        body: event.request.method !== 'GET' && event.request.method !== 'HEAD' ? body : undefined,
                        // @ts-ignore
                        duplex: 'half', // streaming bodyのために必要
                        signal: AbortSignal.timeout(timeout)
                    });
                    console.log(`Response status: ${response.status}`);
                    
                    // レスポンスヘッダーをコピー
                    const responseHeaders = new Headers();
                    response.headers.forEach((value, key) => {
                        responseHeaders.set(key, value);
                    });

                    return new Response(response.body, {
                        status: response.status,
                        statusText: response.statusText,
                        headers: responseHeaders
                    });
                } catch (error) {
                    lastError = error as Error;
                    if (attempt < maxRetries - 1) {
                        // リトライ前に少し待機
                        await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
                        console.log(`Retrying request (attempt ${attempt + 1}/${maxRetries})...`);
                    }
                }
            }
            
            // すべてのリトライが失敗した場合
            throw lastError || new Error('Request failed after retries');
        } catch (error) {
            console.error('Proxy error:', error);
            console.error('Failed URL:', apiUrl);
            return new Response(`Proxy Error: ${error}`, { status: 502 });
        }
    }

    // body size limitを増やす
    return await resolve(event, {
        transformPageChunk: ({ html }) => html
    });
};