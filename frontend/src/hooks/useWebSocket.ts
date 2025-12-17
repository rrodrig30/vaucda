import { useEffect, useRef, useCallback } from 'react'
import { io, Socket } from 'socket.io-client'

// Require VITE_WS_URL to be set - fail fast if not configured
const WS_URL = import.meta.env.VITE_WS_URL
if (!WS_URL) {
  throw new Error(
    'VITE_WS_URL environment variable is required. ' +
    'Set it in your .env file or pass it when running the build.'
  )
}

interface UseWebSocketOptions {
  onMessage?: (data: any) => void
  onConnect?: () => void
  onDisconnect?: () => void
  onError?: (error: any) => void
}

export const useWebSocket = (options: UseWebSocketOptions = {}) => {
  const socketRef = useRef<Socket | null>(null)
  const { onMessage, onConnect, onDisconnect, onError } = options

  useEffect(() => {
    const token = localStorage.getItem('access_token')

    socketRef.current = io(WS_URL, {
      auth: { token },
      transports: ['websocket'],
    })

    const socket = socketRef.current

    socket.on('connect', () => {
      console.log('WebSocket connected')
      onConnect?.()
    })

    socket.on('disconnect', () => {
      console.log('WebSocket disconnected')
      onDisconnect?.()
    })

    socket.on('error', (error: any) => {
      console.error('WebSocket error:', error)
      onError?.(error)
    })

    socket.on('message', (data: any) => {
      onMessage?.(data)
    })

    return () => {
      socket.close()
    }
  }, [onMessage, onConnect, onDisconnect, onError])

  const sendMessage = useCallback((type: string, payload: any) => {
    if (socketRef.current?.connected) {
      socketRef.current.emit('message', { type, payload })
    }
  }, [])

  return {
    sendMessage,
    isConnected: socketRef.current?.connected || false,
  }
}
