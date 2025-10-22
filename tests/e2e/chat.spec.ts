import { expect, test, Page } from '@playwright/test';

test.describe.configure({ mode: 'serial' });

const WAIT_TIMEOUT = 120_000;

type ConversationResult = {
  userMessage: string;
  assistantMessage: string;
};

async function sendMessageAndAwaitResponse(page: Page, message: string): Promise<ConversationResult> {
  const assistantMessages = page.locator('.copilotKitMessage.copilotKitAssistantMessage');
  const initialAssistantCount = await assistantMessages.count();

  const input = page.getByPlaceholder('Type a message...');
  await input.click();
  
  // Type character by character to trigger onChange events properly
  await input.pressSequentially(message, { delay: 50 });
  
  // Give React time to update
  await page.waitForTimeout(500);

  const sendButton = page.getByTestId('copilot-chat-ready');

  console.log('Button disabled:', await sendButton.getAttribute('disabled'));
  console.log('Button visible:', await sendButton.isVisible());
  console.log('Button enabled:', await sendButton.isEnabled());

  // Wait for the button to become enabled (disabled attribute removed)
  //await expect(sendButton).not.toHaveAttribute('disabled', { timeout: 10_000 });
  //await sendButton.click();
  
  await input.press('Enter');

  const userMessageLocator = page
    .locator('.copilotKitMessage.copilotKitUserMessage')
    .filter({ hasText: message });
  await expect(userMessageLocator).toBeVisible({ timeout: WAIT_TIMEOUT });

  await expect(async () => {
    const count = await assistantMessages.count();
    expect(count).toBeGreaterThan(initialAssistantCount);
  }).toPass({ timeout: WAIT_TIMEOUT, intervals: [1_000] });

  const newAssistantMessage = assistantMessages.nth(initialAssistantCount);
  await expect(newAssistantMessage).toBeVisible({ timeout: WAIT_TIMEOUT });

  await expect(async () => {
    const text = (await newAssistantMessage.textContent())?.trim() ?? '';
    expect(text.length).toBeGreaterThan(0);
  }).toPass({ timeout: WAIT_TIMEOUT, intervals: [1_000] });

  const assistantMessageText = ((await newAssistantMessage.textContent()) ?? '').trim();
  return { userMessage: message, assistantMessage: assistantMessageText };
}

function snippet(text: string, length = 80) {
  if (text.length <= length) {
    return text;
  }
  return text.slice(0, length);
}

const uniqueMessage = (prefix: string) => `${prefix} ${Date.now()}-${Math.random().toString(16).slice(2)}`;

test('returns an assistant response when the user sends a message', async ({ page }) => {
  test.slow();
  await page.goto('/');

  const message = uniqueMessage('Playwright message');
  const { assistantMessage } = await sendMessageAndAwaitResponse(page, message);

  expect(assistantMessage.length).toBeGreaterThan(0);
});

test('retains the conversation after reloading the page', async ({ page }) => {
  test.slow();
  await page.goto('/');

  const userMessage = uniqueMessage('Playwright persistence message');
  const { assistantMessage } = await sendMessageAndAwaitResponse(page, userMessage);

  await page.reload();
  await expect(page.getByPlaceholder('Type a message...')).toBeVisible({ timeout: WAIT_TIMEOUT });

  const savedUserMessage = page
    .locator('.copilotKitMessage.copilotKitUserMessage')
    .filter({ hasText: userMessage });
  await expect(savedUserMessage).toBeVisible({ timeout: WAIT_TIMEOUT });

  const assistantSnippet = snippet(assistantMessage, 80);
  await expect(
    page
      .locator('.copilotKitMessage.copilotKitAssistantMessage')
      .filter({ hasText: assistantSnippet })
  ).toBeVisible({ timeout: WAIT_TIMEOUT });
});
