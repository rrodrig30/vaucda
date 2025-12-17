export const isValidEmail = (email: string): boolean => {
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
  return emailRegex.test(email)
}

export const isValidNumber = (value: any): boolean => {
  return !isNaN(parseFloat(value)) && isFinite(value)
}

export const isInRange = (value: number, min: number, max: number): boolean => {
  return value >= min && value <= max
}

export const sanitizeInput = (input: string): string => {
  return input.trim().replace(/[<>]/g, '')
}
