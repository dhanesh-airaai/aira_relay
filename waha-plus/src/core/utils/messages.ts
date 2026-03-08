/**
 * Shared message utilities
 * Extracted from noweb engine for use by GOWS and other components
 */

import type { WAMessageKey } from '@adiwajshing/baileys';
import { toCusFormat } from '@waha/core/utils/jids';
import { MessageDestination } from '@waha/structures/chatting.dto';
import esm from '@waha/vendor/esm';

export function extractMediaContent(
  content: any | null | undefined,
) {
  content = esm.b.extractMessageContent(content);
  const mediaContent =
    content?.documentMessage ||
    content?.imageMessage ||
    content?.videoMessage ||
    content?.audioMessage ||
    content?.ptvMessage ||
    content?.stickerMessage;
  if (mediaContent) {
    return mediaContent;
  }
  if (content?.associatedChildMessage?.message) {
    return extractMediaContent(content.associatedChildMessage.message);
  }
  return null;
}

function extractMessageContent(message) {
  return esm.b.normalizeMessageContent(message);
}

function getContentType(content) {
  return esm.b.getContentType(content);
}

export function extractBody(message): string | null {
  if (!message) {
    return null;
  }
  const content = extractMessageContent(message);
  if (!content) {
    return null;
  }
  let body = content.conversation || null;
  if (!body) {
    body = content.extendedTextMessage?.text;
  }
  if (!body) {
    const mediaContent = extractMediaContent(content);
    // @ts-ignore - AudioMessage doesn't have caption field
    body = mediaContent?.caption;
  }
  if (!body && content.protocolMessage?.editedMessage) {
    body = extractBody(content.protocolMessage.editedMessage);
  }
  if (!body && content.associatedChildMessage?.message) {
    body = extractBody(content.associatedChildMessage.message);
  }
  if (!body) {
    body = content.templateButtonReplyMessage?.selectedDisplayText;
  }
  if (!body) {
    body = content.buttonsResponseMessage?.selectedDisplayText;
  }
  if (!body) {
    const type = getContentType(content);
    if (type == 'listMessage') {
      const list = content.listMessage;
      const parts = [list.title, list.description, list.footerText];
      body = parts.filter(Boolean).join('\n');
    } else if (type === 'listResponseMessage') {
      const response = content.listResponseMessage;
      const parts = [response.title, response.description];
      body = parts.filter(Boolean).join('\n');
    }
  }
  return body;
}

export function buildMessageId({
  id,
  remoteJid,
  fromMe,
  participant,
}: WAMessageKey) {
  const chatId = toCusFormat(remoteJid);
  const parts = [fromMe || false, chatId, id];
  if (participant) {
    parts.push(toCusFormat(participant));
  }
  return parts.join('_');
}

function getTo(key, meId = undefined) {
  const isGroupMessage = Boolean(key.participant);
  if (isGroupMessage) {
    return key.remoteJid;
  }
  if (key.fromMe) {
    return key.remoteJid;
  }
  return meId || 'me';
}

function getFrom(key, meId) {
  const isGroupMessage = Boolean(key.participant);
  if (isGroupMessage) {
    return key.participant;
  }
  if (key.fromMe) {
    return meId || 'me';
  }
  return key.remoteJid;
}

export function getDestination(key, meId = undefined): MessageDestination {
  return {
    id: buildMessageId(key),
    to: toCusFormat(getTo(key, meId)),
    from: toCusFormat(getFrom(key, meId)),
    fromMe: key.fromMe,
  };
}
