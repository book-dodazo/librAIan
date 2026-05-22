import { http } from './httpClient';

export function signup(name, email, password, onboardingData = {}) {
  return http.post('/auth/signup', { name, email, password, onboarding_data: onboardingData });
}

export function login(email, password) {
  return http.post('/auth/login', { email, password });
}
