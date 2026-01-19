import Swal from 'sweetalert2'

// Dark theme colors matching the app
const darkTheme = {
  background: '#1f2937', // gray-800
  text: '#f3f4f6', // gray-100
  confirmButton: '#8b5cf6', // primary-500
  cancelButton: '#4b5563', // gray-600
  denyButton: '#ef4444', // red-500
}

// Base configuration for all alerts
const baseConfig = {
  background: darkTheme.background,
  color: darkTheme.text,
  confirmButtonColor: darkTheme.confirmButton,
  cancelButtonColor: darkTheme.cancelButton,
  denyButtonColor: darkTheme.denyButton,
}

// Toast configuration (corner notifications)
const Toast = Swal.mixin({
  toast: true,
  position: 'bottom-right',
  showConfirmButton: false,
  timer: 5000,
  timerProgressBar: true,
  ...baseConfig,
  didOpen: (toast) => {
    toast.onmouseenter = Swal.stopTimer
    toast.onmouseleave = Swal.resumeTimer
  },
})

// Confirmation dialog configuration
const Confirm = Swal.mixin({
  ...baseConfig,
  showCancelButton: true,
  confirmButtonText: 'Confirm',
  cancelButtonText: 'Cancel',
  reverseButtons: true,
})

// Toast notifications
export const toast = {
  success: (message: string, title?: string) =>
    Toast.fire({
      icon: 'success',
      title: title || message,
      text: title ? message : undefined,
    }),

  error: (message: string, title?: string) =>
    Toast.fire({
      icon: 'error',
      title: title || 'Error',
      text: message,
    }),

  warning: (message: string, title?: string) =>
    Toast.fire({
      icon: 'warning',
      title: title || message,
      text: title ? message : undefined,
    }),

  info: (message: string, title?: string) =>
    Toast.fire({
      icon: 'info',
      title: title || message,
      text: title ? message : undefined,
    }),

  // For loop completion notifications
  loopComplete: (loopName: string, iteration: number, status: 'success' | 'stopped' | 'error') => {
    const icons = {
      success: 'success' as const,
      stopped: 'warning' as const,
      error: 'error' as const,
    }
    const titles = {
      success: 'Loop Completed',
      stopped: 'Loop Stopped',
      error: 'Loop Error',
    }
    return Toast.fire({
      icon: icons[status],
      title: titles[status],
      text: `${loopName} finished at iteration ${iteration}`,
    })
  },
}

// Confirmation dialogs
export const confirm = {
  // Simple yes/no confirmation
  simple: (title: string, text: string) =>
    Confirm.fire({
      title,
      text,
      icon: 'question',
    }),

  // Dangerous action confirmation (red styling)
  danger: (title: string, text: string) =>
    Confirm.fire({
      title,
      text,
      icon: 'warning',
      confirmButtonColor: darkTheme.denyButton,
      confirmButtonText: 'Delete',
    }),

  // Type-to-confirm deletion (like GitHub repo delete)
  typeToDelete: async (itemName: string, itemType: string = 'item') => {
    const result = await Swal.fire({
      ...baseConfig,
      title: `Delete ${itemType}?`,
      html: `
        <div style="text-align: left; color: ${darkTheme.text};">
          <div style="background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px; padding: 12px; margin-bottom: 16px;">
            <p style="color: #f87171; margin: 0; font-size: 14px;">
              This action cannot be undone. This will permanently delete the ${itemType} and all associated data.
            </p>
          </div>
          <p style="margin-bottom: 8px;">
            To confirm, type: <code style="background: #374151; padding: 2px 8px; border-radius: 4px; color: #f87171;">${itemName}</code>
          </p>
        </div>
      `,
      input: 'text',
      inputPlaceholder: `Type ${itemType} name to confirm`,
      inputAttributes: {
        autocapitalize: 'off',
        autocomplete: 'off',
      },
      showCancelButton: true,
      confirmButtonText: 'Delete',
      confirmButtonColor: darkTheme.denyButton,
      cancelButtonText: 'Cancel',
      reverseButtons: true,
      preConfirm: (inputValue) => {
        if (inputValue !== itemName) {
          Swal.showValidationMessage(`Please type "${itemName}" to confirm`)
          return false
        }
        return true
      },
    })

    return result.isConfirmed
  },
}

// Export the raw Swal instance for custom usage
export { Swal }
