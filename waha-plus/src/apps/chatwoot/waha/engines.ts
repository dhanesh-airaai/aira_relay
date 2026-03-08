import { WhatsAppMessage } from '@waha/apps/chatwoot/storage';
import { toCusFormat } from '@waha/core/utils/jids';
import { WAMessage } from '@waha/structures/responses.dto';
import { CallData } from '@waha/structures/calls.dto';

interface IEngineHelper {
  ChatID(message: WAMessage | any): string;

  CallChatID(call: CallData | any): string;

  WhatsAppMessageKeys(message: any): WhatsAppMessage;

  IterateMessages<T extends { timestamp: number }>(
    messages: AsyncGenerator<T>,
  ): AsyncGenerator<T>;

  ContactIsMy(contact);

  FilterChatIdsForMessages(chats: string[]): string[];

  SupportsAllChatForMessage(): boolean;
}

class GOWSHelper implements IEngineHelper {
  ChatID(message: WAMessage): string {
    return message.from;
  }

  CallChatID(call: CallData): string {
    return call._data?.CallCreator || call.from;
  }

  /**
   * Parse API response and get the data
   * API Response depends on engine right now
   */
  WhatsAppMessageKeys(message: any): WhatsAppMessage {
    const Info = message._data.Info;
    const timestamp = new Date(Info.Timestamp).getTime();
    return {
      timestamp: new Date(timestamp),
      from_me: Info.IsFromMe,
      chat_id: toCusFormat(Info.Chat),
      message_id: Info.ID,
      participant: Info.Sender ? toCusFormat(Info.Sender) : null,
    };
  }

  IterateMessages<T extends { timestamp: number }>(
    messages: AsyncGenerator<T>,
  ): AsyncGenerator<T> {
    return messages;
  }

  FilterChatIdsForMessages(chats: string[]): string[] {
    return chats;
  }

  SupportsAllChatForMessage(): boolean {
    return true;
  }

  ContactIsMy(contact) {
    return true;
  }
}

export const EngineHelper: IEngineHelper = new GOWSHelper();
