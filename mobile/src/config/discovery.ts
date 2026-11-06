import { authConfig } from './auth';

export const discoveryConfig = {
  apiUrl: authConfig.apiUrl,
  timeoutMs: authConfig.timeoutMs,
  minIdeaLength: 2,
  maxIdeaLength: 1000,
  summaryTimeoutMs: 20000,
  summaryMaxBytes: 32768,
  summaryMaxChars: 8000,
  pageSize: 20,
  maxPageSize: 50,
  cachePrefix: 'reporadar.discovery',
};
