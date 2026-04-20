import React from 'react'

export default function ErrorTest() {
  const [shouldError, setShouldError] = React.useState(false)

  if (shouldError) {
    throw new Error('Test error from ErrorTest component')
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Error Boundary Test</h1>
      <button
        onClick={() => setShouldError(true)}
        className="px-4 py-2 bg-red-600 text-white rounded"
        data-testid="trigger-error"
      >
        Trigger Error
      </button>
    </div>
  )
}
