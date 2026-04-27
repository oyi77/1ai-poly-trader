import React from 'react';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ErrorBoundary } from '../ErrorBoundary';

const originalError = console.error;
const installFetchMock = (fetchMock: ReturnType<typeof vi.fn>) => {
  window.fetch = Object.assign(fetchMock, {
    preconnect: vi.fn(),
  }) as unknown as typeof fetch;
};

beforeEach(() => {
  console.error = vi.fn();
});

afterEach(() => {
  console.error = originalError;
});

const ThrowingComponent = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) {
    throw new Error('Test render error');
  }
  return <div>Safe content</div>;
};

class LifecycleThrowingComponent extends React.Component {
  componentDidMount() {
    throw new Error('Test lifecycle error');
  }

  render() {
    return <div>Lifecycle component</div>;
  }
}

const AsyncThrowingComponent = () => {
  const [shouldThrow, setShouldThrow] = React.useState(false);

  React.useEffect(() => {
    if (shouldThrow) {
      throw new Error('Test async error');
    }
  }, [shouldThrow]);

  return (
    <div>
      <button onClick={() => setShouldThrow(true)}>Trigger async error</button>
      Async component
    </div>
  );
};

describe('ErrorBoundary', () => {
  describe('Render Error Catching', () => {
    it('should catch render errors and display fallback UI', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(screen.getByText(/An unexpected error occurred/)).toBeInTheDocument();
    });

    it('should display error message in fallback UI', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Error Message:')).toBeInTheDocument();
      expect(screen.getByText(/Test render error/)).toBeInTheDocument();
    });

    it('should render children when no error occurs', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={false} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Safe content')).toBeInTheDocument();
      expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    });

    it('should display reload button in fallback UI', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const reloadButton = screen.getByRole('button', { name: /Reload Page/i });
      expect(reloadButton).toBeInTheDocument();
    });
  });

  describe('Lifecycle Error Catching', () => {
    it('should catch componentDidMount errors', () => {
      render(
        <ErrorBoundary>
          <LifecycleThrowingComponent />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
      expect(screen.getByText(/Test lifecycle error/)).toBeInTheDocument();
    });

    it('should display component stack in dev mode', () => {
      render(
        <ErrorBoundary>
          <LifecycleThrowingComponent />
        </ErrorBoundary>
      );

      if (import.meta.env.DEV) {
        expect(screen.getByText('Component Stack:')).toBeInTheDocument();
      }
    });
  });

  describe('Async Error Handling', () => {
    it('should handle errors thrown in useEffect', async () => {
      render(
        <ErrorBoundary>
          <AsyncThrowingComponent />
        </ErrorBoundary>
      );

      const triggerButton = screen.getByRole('button', { name: /Trigger async error/i });
      fireEvent.click(triggerButton);

      await waitFor(() => {
        expect(console.error).toHaveBeenCalled();
      });
    });
  });

  describe('Reload Button Functionality', () => {
    it('should display reload button when error occurs', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const reloadButton = screen.getByRole('button', { name: /Reload Page/i });
      expect(reloadButton).toBeInTheDocument();
    });

    it('should call handleReload when reload button is clicked', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();

      const reloadButton = screen.getByRole('button', { name: /Reload Page/i });
      fireEvent.click(reloadButton);

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });
  });

  describe('Backend Error Reporting', () => {
    it('should report errors to backend', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        statusText: 'OK',
      });
      installFetchMock(fetchMock);

      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      await waitFor(() => {
        expect(fetchMock).toHaveBeenCalledWith(
          '/api/v1/errors/frontend',
          expect.objectContaining({
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
          })
        );
      });
    });

    it('should include error details in backend report', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        statusText: 'OK',
      });
      installFetchMock(fetchMock);

      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      await waitFor(() => {
        const call = fetchMock.mock.calls[0];
        const body = JSON.parse(call[1].body);

        expect(body).toHaveProperty('message');
        expect(body).toHaveProperty('stack');
        expect(body).toHaveProperty('componentStack');
        expect(body).toHaveProperty('timestamp');
        expect(body).toHaveProperty('userAgent');
        expect(body.message).toContain('Test render error');
      });
    });

    it('should handle backend reporting failures gracefully', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
      });
      installFetchMock(fetchMock);

      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      await waitFor(() => {
        expect(vi.mocked(console.error).mock.calls).toEqual(expect.arrayContaining([[
          'Failed to report error to backend:',
          'Internal Server Error',
        ]]));
      });
    });

    it('should handle network errors during reporting', async () => {
      const fetchMock = vi.fn().mockRejectedValue(new Error('Network error'));
      installFetchMock(fetchMock);

      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      await waitFor(() => expect(fetchMock).toHaveBeenCalled());
      await waitFor(() => {
        expect(vi.mocked(console.error).mock.calls).toEqual(
          expect.arrayContaining([
            ['Error reporting to backend:', expect.any(Error)],
          ])
        );
      });
    });

    it('should include userAgent in error report', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        statusText: 'OK',
      });
      installFetchMock(fetchMock);

      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      await waitFor(() => {
        const call = fetchMock.mock.calls[0];
        const body = JSON.parse(call[1].body);

        expect(body.userAgent).toBe(navigator.userAgent);
      });
    });

    it('should include timestamp in error report', async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        statusText: 'OK',
      });
      installFetchMock(fetchMock);

      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      await waitFor(() => {
        const call = fetchMock.mock.calls[0];
        const body = JSON.parse(call[1].body);

        expect(body.timestamp).toBeDefined();
        expect(new Date(body.timestamp)).toBeInstanceOf(Date);
      });
    });
  });

  describe('Error Boundary State Management', () => {
    it('should maintain error state across re-renders', () => {
      const { rerender } = render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();

      rerender(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('should have error and errorInfo in state after catching error', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      expect(screen.getByText(/Test render error/)).toBeInTheDocument();
      expect(screen.getByText('Error Message:')).toBeInTheDocument();
    });
  });

  describe('Fallback UI Styling', () => {
    it('should render fallback UI with correct structure', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const heading = screen.getByText('Something went wrong');
      expect(heading).toBeInTheDocument();
      expect(heading).toHaveClass('text-2xl', 'font-bold');
    });

    it('should display error icon in fallback UI', () => {
      render(
        <ErrorBoundary>
          <ThrowingComponent shouldThrow={true} />
        </ErrorBoundary>
      );

      const svg = screen.getByText('Something went wrong').closest('div')?.querySelector('svg');
      expect(svg).toBeInTheDocument();
    });
  });
});
