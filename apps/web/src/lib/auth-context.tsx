"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import {
  clearTokens,
  getAccessToken,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
  setTokens,
  type LoginPayload,
  type RegisterPayload,
  type UserPublic,
} from "@/lib/api";

interface AuthState {
  user: UserPublic | null;
  loading: boolean;
  signIn: (payload: LoginPayload) => Promise<UserPublic>;
  signUp: (payload: RegisterPayload) => Promise<UserPublic>;
  signOut: () => Promise<void>;
  isAuthenticated: boolean;
  isAdmin: boolean;
}

const AuthContext = createContext<AuthState | null>(null);

const USER_KEY = "nodrat_user";

function loadCachedUser(): UserPublic | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserPublic;
  } catch {
    return null;
  }
}

function cacheUser(user: UserPublic | null) {
  if (typeof window === "undefined") return;
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  } else {
    localStorage.removeItem(USER_KEY);
  }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserPublic | null>(null);
  const [loading, setLoading] = useState(true);

  // Initial load — token + cached user
  useEffect(() => {
    const token = getAccessToken();
    const cached = loadCachedUser();
    if (token && cached) {
      setUser(cached);
    }
    setLoading(false);
  }, []);

  const signIn = useCallback(
    async (payload: LoginPayload): Promise<UserPublic> => {
      const response = await apiLogin(payload);
      setTokens(response.access_token, response.refresh_token);
      cacheUser(response.user);
      setUser(response.user);
      return response.user;
    },
    [],
  );

  const signUp = useCallback(
    async (payload: RegisterPayload): Promise<UserPublic> => {
      const response = await apiRegister(payload);
      setTokens(response.access_token, response.refresh_token);
      cacheUser(response.user);
      setUser(response.user);
      return response.user;
    },
    [],
  );

  const signOut = useCallback(async () => {
    await apiLogout();
    clearTokens();
    cacheUser(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn,
      signUp,
      signOut,
      isAuthenticated: user !== null,
      isAdmin: user?.role === "super_admin",
    }),
    [user, loading, signIn, signUp, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (ctx === null) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
