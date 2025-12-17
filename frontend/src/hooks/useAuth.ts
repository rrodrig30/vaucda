import { useAppSelector } from '@/store/hooks'

export const useAuth = () => {
  const { user, isAuthenticated, isLoading, error } = useAppSelector((state) => state.auth)

  return {
    user,
    isAuthenticated,
    isLoading,
    error,
    isAdmin: user?.role === 'admin',
  }
}
