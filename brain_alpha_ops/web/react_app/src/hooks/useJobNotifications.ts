export function sendCompletionNotification(title: string, body: string): void {
  try {
    if (document.hidden && Notification.permission === 'granted') {
      new Notification(title, { body });
    }
  } catch {
    console.warn('useJobState: Notification API not available');
  }
}

export function requestNotificationPermission(): void {
  try {
    if (Notification.permission === 'default') {
      Notification.requestPermission();
    }
  } catch {
    console.warn('useJobState: Notification API not available');
  }
}

export interface JobNotifications {
  sendCompletionNotification: (title: string, body: string) => void;
  requestNotificationPermission: () => void;
}

export function useJobNotifications(): JobNotifications {
  return {
    sendCompletionNotification,
    requestNotificationPermission,
  };
}
