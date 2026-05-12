export async function addUnifiedQueueEntry(params) {
  const options = params && typeof params === 'object' ? params : {};
  const queueApiBase = String(options.queueApiBase || '').trim();
  const printerId = String(options.printerId || '').trim();
  const payload = options.payload && typeof options.payload === 'object' ? options.payload : {};

  if (!queueApiBase) {
    throw new Error('Queue API base URL is required.');
  }
  if (!printerId) {
    throw new Error('Printer ID is required.');
  }

  const response = await fetch(
    `${queueApiBase}/queues/${encodeURIComponent(printerId)}/add`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    }
  );

  const responseBody = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(String(responseBody.message || responseBody.error || `Queue add failed (${response.status})`));
  }
  return responseBody;
}