import { createContext, use } from 'react';

import type { SessionStatus } from '@/shared/api/session';
import type { User } from '@/shared/api/types';

import type { LoginRequest, RegisterRequest } from './api';

export interface AuthContextValue {
  status: SessionStatus;
  user: User | null;
  login: (credentials: LoginRequest) => Promise<User>;
  /** Регистрация и сразу вход: сервер токены при регистрации не выдает. */
  register: (data: RegisterRequest) => Promise<User>;
  logout: () => Promise<void>;
  /** Повторить стартовую проверку сессии после сбоя сети. */
  retry: () => Promise<void>;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = use(AuthContext);
  if (!value) throw new Error('useAuth вызван вне AuthProvider');
  return value;
}
