import { Navigate } from 'react-router-dom';
import { getUser } from '../../utils/storage';

/**
 * 로그인 여부를 확인하고 미로그인 시 /login으로 리다이렉트합니다.
 * App.jsx의 라우트를 이 컴포넌트로 감싸면 보호됩니다.
 */
export default function ProtectedRoute({ children }) {
  const user = getUser();
  return user ? children : <Navigate to="/login" replace />;
}
