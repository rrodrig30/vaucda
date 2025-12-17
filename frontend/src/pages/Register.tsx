import React, { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useNavigate, Link } from 'react-router-dom'
import { useAppDispatch, useAppSelector } from '@/store/hooks'
import { register as registerAction, clearError } from '@/store/slices/authSlice'
import { Button } from '@/components/common/Button'
import { Input } from '@/components/common/Input'
import { Select } from '@/components/common/Select'
import { Alert } from '@/components/common/Alert'

// Validation schema matching backend requirements
const registerSchema = z.object({
  email: z.string().email('Invalid email address'),
  password: z
    .string()
    .min(8, 'Password must be at least 8 characters')
    .regex(/[A-Z]/, 'Password must contain at least one uppercase letter')
    .regex(/[a-z]/, 'Password must contain at least one lowercase letter')
    .regex(/\d/, 'Password must contain at least one digit'),
  confirmPassword: z.string(),
  firstName: z.string().min(1, 'First name is required').max(100),
  lastName: z.string().min(1, 'Last name is required').max(100),
  initials: z
    .string()
    .min(1, 'Initials are required')
    .max(10)
    .regex(/^[A-Z\s]+$/, 'Initials must be uppercase letters only'),
  position: z.enum([
    'Physician-Faculty',
    'Physician-Fellow',
    'Physician-Resident',
    'APP-PA',
    'APP-NP',
    'Staff',
  ]),
  specialty: z.enum(['Urology', 'ENT', 'Hospital Medicine']),
  openevidenceUsername: z.string().max(255).optional().or(z.literal('')),
  openevidencePassword: z.string().max(255).optional().or(z.literal('')),
}).refine((data) => data.password === data.confirmPassword, {
  message: "Passwords don't match",
  path: ['confirmPassword'],
})

type RegisterFormData = z.infer<typeof registerSchema>

const positionOptions = [
  { value: '', label: 'Select Position' },
  { value: 'Physician-Faculty', label: 'Physician - Faculty' },
  { value: 'Physician-Fellow', label: 'Physician - Fellow' },
  { value: 'Physician-Resident', label: 'Physician - Resident' },
  { value: 'APP-PA', label: 'APP - PA' },
  { value: 'APP-NP', label: 'APP - NP' },
  { value: 'Staff', label: 'Staff' },
]

const specialtyOptions = [
  { value: '', label: 'Select Specialty' },
  { value: 'Urology', label: 'Urology' },
  { value: 'ENT', label: 'ENT' },
  { value: 'Hospital Medicine', label: 'Hospital Medicine' },
]

export const Register: React.FC = () => {
  const dispatch = useAppDispatch()
  const navigate = useNavigate()
  const { isLoading, error } = useAppSelector((state) => state.auth)
  const [showOpenEvidence, setShowOpenEvidence] = useState(false)

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      position: '' as any,
      specialty: '' as any,
      openevidenceUsername: '',
      openevidencePassword: '',
    },
  })

  const onSubmit = async (data: RegisterFormData) => {
    // Prepare registration data
    const registrationData = {
      email: data.email,
      password: data.password,
      first_name: data.firstName,
      last_name: data.lastName,
      initials: data.initials.toUpperCase(),
      position: data.position,
      specialty: data.specialty,
      openevidence_username: data.openevidenceUsername || undefined,
      openevidence_password: data.openevidencePassword || undefined,
    }

    const result = await dispatch(registerAction(registrationData))
    if (registerAction.fulfilled.match(result)) {
      // Registration successful, redirect to login
      navigate('/login')
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary to-secondary p-4">
      <div className="max-w-2xl w-full bg-white dark:bg-gray-800 rounded-lg shadow-heavy p-8">
        <div className="text-center mb-8">
          <img src="/logo.svg" alt="VAUCDA Logo" className="h-16 w-16 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-primary">Create Your Account</h1>
          <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
            VA Urology Clinical Documentation Assistant
          </p>
        </div>

        {error && (
          <Alert
            type="error"
            message={error}
            onClose={() => dispatch(clearError())}
            className="mb-4"
          />
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          {/* Personal Information */}
          <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Personal Information
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                {...register('firstName')}
                label="First Name"
                type="text"
                placeholder="Enter your first name"
                error={errors.firstName?.message}
                required
              />

              <Input
                {...register('lastName')}
                label="Last Name"
                type="text"
                placeholder="Enter your last name"
                error={errors.lastName?.message}
                required
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
              <Input
                {...register('initials')}
                label="Initials"
                type="text"
                placeholder="e.g., RR"
                error={errors.initials?.message}
                helpText="Uppercase letters only"
                required
                maxLength={10}
                style={{ textTransform: 'uppercase' }}
              />

              <Input
                {...register('email')}
                label="Email"
                type="email"
                placeholder="your.email@uthscsa.edu"
                error={errors.email?.message}
                autoComplete="email"
                required
              />
            </div>
          </div>

          {/* Professional Information */}
          <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Professional Information
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Select
                {...register('position')}
                label="Position"
                options={positionOptions}
                error={errors.position?.message}
                required
              />

              <Select
                {...register('specialty')}
                label="Specialty"
                options={specialtyOptions}
                error={errors.specialty?.message}
                required
              />
            </div>
          </div>

          {/* Account Security */}
          <div className="border-b border-gray-200 dark:border-gray-700 pb-4">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">
              Account Security
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                {...register('password')}
                label="Password"
                type="password"
                placeholder="Create a password"
                error={errors.password?.message}
                autoComplete="new-password"
                helpText="Min 8 chars, 1 uppercase, 1 lowercase, 1 digit"
                required
              />

              <Input
                {...register('confirmPassword')}
                label="Confirm Password"
                type="password"
                placeholder="Confirm your password"
                error={errors.confirmPassword?.message}
                autoComplete="new-password"
                required
              />
            </div>
          </div>

          {/* OpenEvidence Credentials (Optional) */}
          <div className="pb-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
                OpenEvidence Credentials (Optional)
              </h2>
              <button
                type="button"
                onClick={() => setShowOpenEvidence(!showOpenEvidence)}
                className="text-sm text-primary hover:text-primary-dark"
              >
                {showOpenEvidence ? 'Hide' : 'Show'}
              </button>
            </div>

            {showOpenEvidence && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input
                  {...register('openevidenceUsername')}
                  label="OpenEvidence Username"
                  type="text"
                  placeholder="Optional"
                  error={errors.openevidenceUsername?.message}
                />

                <Input
                  {...register('openevidencePassword')}
                  label="OpenEvidence Password"
                  type="password"
                  placeholder="Optional"
                  error={errors.openevidencePassword?.message}
                  helpText="Stored securely with encryption"
                />
              </div>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            fullWidth
            isLoading={isLoading}
          >
            Create Account
          </Button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600 dark:text-gray-400">
            Already have an account?{' '}
            <Link
              to="/login"
              className="text-primary hover:text-primary-dark font-medium"
            >
              Sign in here
            </Link>
          </p>
        </div>

        <div className="mt-4 text-center text-sm text-gray-600 dark:text-gray-400">
          <p>Secure VA System - Authorized Access Only</p>
        </div>
      </div>
    </div>
  )
}
