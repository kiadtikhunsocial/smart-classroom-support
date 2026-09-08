export interface User {
  id: number;
  line_user_id: string;
  line_display_name: string | null;
  line_picture_url: string | null;
  line_email: string | null;
  organization_id: number | null;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  organization?: Organization | null;
}

export type UserRole = 'admin' | 'teacher' | 'it_support' | 'student' | 'super_admin';

export interface Organization {
  id: number;
  code: string;
  name: string;
  short_name: string | null;
  timezone: string;
}

export interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}
