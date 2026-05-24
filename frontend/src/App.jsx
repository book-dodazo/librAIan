import { Routes, Route, Navigate } from 'react-router-dom';
import { ProtectedRoute } from './components/common';
import LoginPage from './pages/LoginPage';
import ChatPage from './pages/ChatPage';
import FeedbackPage from './pages/FeedbackPage';
import ProfilePage from './pages/ProfilePage';
import OnboardingFlow from './pages/OnboardingFlow';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/chat"     element={<ChatPage />} />
      <Route path="/feedback" element={<ProtectedRoute><FeedbackPage /></ProtectedRoute>} />
      <Route path="/profile"  element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
      <Route path="/dev/onboarding" element={
        <div className="min-h-screen bg-paper flex items-center justify-center px-4">
          <div className="w-full max-w-sm">
            <OnboardingFlow onComplete={(data) => console.log('onboarding result:', data)} loading={false} />
          </div>
        </div>
      } />
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
