import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { User, AuthState } from './types/user';

const AuthContext = createContext<AuthState>({
  user: null,
  isLoading: true,
  isAuthenticated: false,
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // ตรวจสอบสถานะการล็อกอินจาก localStorage
    const stored = localStorage.getItem('sc_user');
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        localStorage.removeItem('sc_user');
      }
    }
    setIsLoading(false);
  }, []);

  const login = (userData: User) => {
    setUser(userData);
    localStorage.setItem('sc_user', JSON.stringify(userData));
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem('sc_user');
    // Redirect ไปหน้า login
    window.location.href = '/login';
  };

  return (
    <AuthContext.Provider value={{ user, isLoading, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}

// Hook สำหรับเช็คสิทธิ์ตาม role
export function usePermission(allowedRoles: string[]) {
  const { user, isAuthenticated } = useAuth();
  if (!isAuthenticated || !user) return false;
  return allowedRoles.includes(user.role);
}
