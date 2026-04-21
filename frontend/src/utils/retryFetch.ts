interface RetryOptions {
  maxAttempts?: number;
  backoffDelays?: number[];
}

const DEFAULT_OPTIONS: Required<RetryOptions> = {
  maxAttempts: 3,
  backoffDelays: [1000, 2000, 4000],
};

function shouldRetry(error: unknown, response?: Response): boolean {
  if (error instanceof TypeError && error.message.includes('fetch')) {
    return true;
  }

  if (response && response.status >= 500 && response.status < 600) {
    return true;
  }

  if (response && response.status >= 400 && response.status < 500) {
    return false;
  }

  return true;
}

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

export async function retryFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
  options: RetryOptions = {}
): Promise<Response> {
  const { maxAttempts, backoffDelays } = { ...DEFAULT_OPTIONS, ...options };
  
  let lastError: unknown;
  let lastResponse: Response | undefined;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    try {
      const response = await fetch(input, init);
      
      if (response.ok) {
        return response;
      }

      if (!shouldRetry(null, response)) {
        return response;
      }

      lastResponse = response;

      if (attempt < maxAttempts - 1) {
        const delay = backoffDelays[attempt] || backoffDelays[backoffDelays.length - 1];
        console.warn(
          `Request failed with status ${response.status}. Retrying in ${delay}ms... (attempt ${attempt + 1}/${maxAttempts})`
        );
        await sleep(delay);
      }
    } catch (error) {
      lastError = error;

      if (!shouldRetry(error)) {
        throw error;
      }

      if (attempt < maxAttempts - 1) {
        const delay = backoffDelays[attempt] || backoffDelays[backoffDelays.length - 1];
        console.warn(
          `Request failed with error: ${error}. Retrying in ${delay}ms... (attempt ${attempt + 1}/${maxAttempts})`
        );
        await sleep(delay);
      }
    }
  }

  if (lastResponse) {
    return lastResponse;
  }

  throw lastError || new Error('All retry attempts failed');
}

export async function retryFetchJson<T = any>(
  input: RequestInfo | URL,
  init?: RequestInit,
  options?: RetryOptions
): Promise<T> {
  const response = await retryFetch(input, init, options);
  
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }
  
  return response.json();
}
