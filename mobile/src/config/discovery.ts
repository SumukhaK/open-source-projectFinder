import { authConfig } from './auth';

export const discoveryConfig = {
  apiUrl: authConfig.apiUrl,
  timeoutMs: authConfig.timeoutMs,
  minIdeaLength: 2,
  maxIdeaLength: 1000,
  maxPage: 50,
  pageSize: 20,
  cachePrefix: 'reporadar.discovery',
};
