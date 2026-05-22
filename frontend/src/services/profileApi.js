import { http } from './httpClient';

export function getProfile() {
  return http.get('/profile');
}

export function updateProfile(onboardingData) {
  return http.put('/profile', { onboarding_data: onboardingData });
}

export function addFeedback(feedback) {
  return http.post('/profile/feedback', { feedback });
}
