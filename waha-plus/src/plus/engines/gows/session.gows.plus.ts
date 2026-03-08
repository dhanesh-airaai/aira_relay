import { UnprocessableEntityException } from '@nestjs/common';
import { Jid } from '@waha/core/engines/const';
import { messages } from '@waha/core/engines/gows/grpc/gows';
import { parseJson } from '@waha/core/engines/gows/helpers';
import {
  getMessageIdFromSerialized,
  WhatsappSessionGoWSCore,
} from '@waha/core/engines/gows/session.gows.core';
import { NotImplementedByEngineError } from '@waha/core/exceptions';
import { WAMimeType } from '@waha/core/media/WAMimeType';
import { parseMessageIdSerialized } from '@waha/core/utils/ids';
import {
  isJidGroup,
  isJidBroadcast,
  isJidNewsletter,
  toJID,
} from '@waha/core/utils/jids';
import { sortObjectByValues } from '@waha/helpers';
import { GowsAuthFactoryPlus } from '@waha/plus/engines/gows/store/GowsAuthFactoryPlus';
import { Ffmpeg } from '@waha/plus/utils/ffmpeg';
import {
  Channel,
  ChannelListResult,
  ChannelMessage,
  ChannelSearchByText,
  ChannelSearchByView,
  CreateChannelRequest,
  PreviewChannelMessages,
} from '@waha/structures/channels.dto';
import {
  MessageButtonReply,
  MessageFileRequest,
  MessageImageRequest,
  MessageLinkCustomPreviewRequest,
  MessagePollVoteRequest,
  MessageVideoRequest,
  MessageVoiceRequest,
} from '@waha/structures/chatting.dto';
import { SendListRequest } from '@waha/structures/chatting.list.dto';
import { BinaryFile, RemoteFile } from '@waha/structures/files.dto';
import {
  ImageStatus,
  VideoStatus,
  VoiceStatus,
} from '@waha/structures/status.dto';
import esm from '@waha/vendor/esm';
import axios from 'axios';
import axiosRetry from 'axios-retry';
import { promisify } from 'util';
import { Activity } from '@waha/core/abc/activity';
import { TmpDir } from '@waha/utils/tmpdir';
import * as path from 'path';
import * as fsp from 'fs/promises';

axiosRetry(axios, { retries: 3 });

export class WhatsappSessionGoWSPlus extends WhatsappSessionGoWSCore {
  protected authFactory = new GowsAuthFactoryPlus();

  constructor(config) {
    super(config);
    this.mediaConverter = new Ffmpeg(this.name, this.logger);
  }

  private async fileToMedia(
    file: RemoteFile | BinaryFile,
  ): Promise<messages.Media> {
    let content: Buffer;
    if ('url' in file) {
      // fetch file
      content = await this.fetch(file.url);
    } else {
      // base64 to bytes
      content = Buffer.from(file.data, 'base64');
    }

    return new messages.Media({
      content: content,
      mimetype: file.mimetype,
      filename: file.filename,
    });
  }

  /**
   * Send methods
   */
  @Activity()
  async sendList(request: SendListRequest): Promise<any> {
    const jid = toJID(this.ensureSuffix(request.chatId));
    if (isJidGroup(jid) || isJidBroadcast(jid) || isJidNewsletter(jid)) {
      throw new UnprocessableEntityException(
        `List message can only be sent to a direct message chat.`,
      );
    }
    const m = request.message;
    const list = messages.ListMessage.fromObject({
      title: m.title,
      description: m.description,
      footer: m.footer,
      button: m.button,
      sections: m.sections,
    });
    const message = new messages.MessageRequest({
      jid: jid,
      session: this.session,
      replyTo: getMessageIdFromSerialized(request.reply_to),
      list: list,
    });
    const response = await promisify(this.client.SendMessage)(message);
    const data = response.toObject();
    return this.messageResponse(jid, data);
  }

  /**
   * Profile methods
   */
  @Activity()
  protected async setProfilePicture(
    file: BinaryFile | RemoteFile,
  ): Promise<boolean> {
    const media = await this.fileToMedia(file);
    const request = new messages.SetProfilePictureRequest({
      session: this.session,
      picture: media.content,
    });
    const response = await promisify(this.client.SetProfilePicture)(request);
    response.toObject();
    return true;
  }

  protected async deleteProfilePicture(): Promise<boolean> {
    const request = new messages.SetProfilePictureRequest({
      session: this.session,
    });
    const response = await promisify(this.client.SetProfilePicture)(request);
    response.toObject();
    return true;
  }

  /**
   * Groups methods
   */
  @Activity()
  protected async setGroupPicture(
    id: string,
    file: BinaryFile | RemoteFile,
  ): Promise<boolean> {
    const media = await this.fileToMedia(file);
    const request = new messages.SetPictureRequest({
      session: this.session,
      jid: id,
      picture: media.content,
    });
    const response = await promisify(this.client.SetGroupPicture)(request);
    response.toObject();
    return true;
  }

  @Activity()
  protected async deleteGroupPicture(id: string): Promise<boolean> {
    const request = new messages.SetPictureRequest({
      session: this.session,
      jid: id,
    });
    const response = await promisify(this.client.SetGroupPicture)(request);
    response.toObject();
    return true;
  }

  /**
   * Send media methods
   */
  private async sendMedia(type: messages.MediaType, request: any) {
    const jid = toJID(this.ensureSuffix(request.chatId));
    const media = await this.fileToMedia(request.file);
    media.type = type;

    if (request.convert) {
      switch (type) {
        case messages.MediaType.AUDIO:
          media.content = await this.mediaConverter.voice(
            media.content as Buffer,
          );
          media.mimetype = WAMimeType.VOICE;
          break;
        case messages.MediaType.VIDEO:
          media.content = await this.mediaConverter.video(
            media.content as Buffer,
          );
          media.mimetype = WAMimeType.VIDEO;
          break;
        case messages.MediaType.PTV:
          media.content = await this.mediaConverter.video(
            media.content as Buffer,
          );
          media.mimetype = WAMimeType.VIDEO;
          break;
        default:
          this.logger.warn(`No conversion for ${type}`);
          break;
      }
    }

    // Only for Voice Status
    let backgroundColor: messages.OptionalString | null = null;
    if (request.backgroundColor) {
      backgroundColor = new messages.OptionalString({
        value: request.backgroundColor,
      });
    }
    const participants = await this.prepareJidsForStatus(request.contacts);
    const message = new messages.MessageRequest({
      id: request.id,
      jid: jid,
      text: request.caption,
      session: this.session,
      media: media,
      backgroundColor: backgroundColor,
      mentions: request.mentions?.map((mention) => toJID(mention)),
      participants: participants,
    });

    if (media.type == messages.MediaType.AUDIO) {
      const logger: any = this.loggerBuilder.child({});
      const buffer = Buffer.from(media.content);
      const waveform = await esm.b.getAudioWaveform(buffer, logger);
      const duration = await esm.b.getAudioDuration(buffer);
      media.audio = new messages.AudioInfo({
        waveform: waveform,
        duration: duration,
      });
    }

    message.replyTo = getMessageIdFromSerialized(request.reply_to);
    const tmpdir = new TmpDir(this.logger, `waha-smedia-${this.name}-`);
    return await tmpdir.use(async (dir) => {
      const file = path.join(dir, 'send-media.tmp');
      // Try to write to the file
      try {
        await fsp.writeFile(file, Buffer.from(media.content));
        media.contentPath = file;
        media.content = null;
      } catch (e) {
        this.logger.error(`Failed to write media to temp file: ${e.message}`);
      }
      const response = await promisify(this.client.SendMessage)(message);
      const data = response.toObject();
      return this.messageResponse(jid, data);
    });
  }

  @Activity()
  async sendImage(request: MessageImageRequest) {
    return await this.sendMedia(messages.MediaType.IMAGE, request);
  }

  @Activity()
  async sendFile(request: MessageFileRequest) {
    return await this.sendMedia(messages.MediaType.DOCUMENT, request);
  }

  @Activity()
  async sendVoice(request: MessageVoiceRequest) {
    return await this.sendMedia(messages.MediaType.AUDIO, request);
  }

  @Activity()
  async sendVideo(request: MessageVideoRequest) {
    const type = request.asNote
      ? messages.MediaType.PTV
      : messages.MediaType.VIDEO;
    return await this.sendMedia(type, request);
  }

  @Activity()
  async sendPollVote(request: MessagePollVoteRequest) {
    const jid = toJID(this.ensureSuffix(request.chatId));
    const key = parseMessageIdSerialized(request.pollMessageId, true);
    const pollVote = new messages.PollVoteMessage({
      pollMessageId: key.id,
      options: request.votes,
    });
    if (request.pollServerId != null) {
      // protobuf expects int64 number
      pollVote.pollServerId = request.pollServerId;
    }
    const message = new messages.MessageRequest({
      jid: jid,
      session: this.session,
      pollVote: pollVote,
    });
    const response = await promisify(this.client.SendMessage)(message);
    const data = response.toObject();
    return this.messageResponse(jid, data);
  }

  @Activity()
  async sendLinkCustomPreview(
    request: MessageLinkCustomPreviewRequest,
  ): Promise<any> {
    const jid = toJID(this.ensureSuffix(request.chatId));
    const media = await this.fileToMedia(request.preview.image as RemoteFile);
    const preview = new messages.LinkPreview({
      url: request.preview.url,
      title: request.preview.title,
      description: request.preview.description,
      image: media.content,
    });
    const message = new messages.MessageRequest({
      jid: jid,
      text: request.text,
      session: this.session,
      linkPreview: true,
      linkPreviewHighQuality: request.linkPreviewHighQuality,
      replyTo: getMessageIdFromSerialized(request.reply_to),
      preview: preview,
    });
    const response = await promisify(this.client.SendMessage)(message);
    const data = response.toObject();
    return this.messageResponse(jid, data);
  }

  @Activity()
  async sendButtonsReply(request: MessageButtonReply) {
    throw new NotImplementedByEngineError();

    // Doesn't work yet
    const jid = toJID(this.ensureSuffix(request.chatId));
    const message = new messages.ButtonReplyRequest({
      jid: jid,
      session: this.session,
      replyTo: getMessageIdFromSerialized(request.replyTo),
      selectedDisplayText: request.selectedDisplayText,
      selectedButtonID: request.selectedButtonID,
    });
    const response = await promisify(this.client.SendButtonReply)(message);
    const data = response.toObject();
    return this.messageResponse(jid, data);
  }

  /**
   * Status methods
   */
  @Activity()
  public async sendImageStatus(status: ImageStatus) {
    const request = {
      ...status,
      chatId: Jid.BROADCAST,
    };
    return await this.sendMedia(messages.MediaType.IMAGE, request);
  }

  @Activity()
  public async sendVoiceStatus(status: VoiceStatus) {
    const request = {
      ...status,
      chatId: Jid.BROADCAST,
    };
    return await this.sendMedia(messages.MediaType.AUDIO, request);
  }

  @Activity()
  public async sendVideoStatus(status: VideoStatus) {
    const request = {
      ...status,
      chatId: Jid.BROADCAST,
    };
    return await this.sendMedia(messages.MediaType.VIDEO, request);
  }

  @Activity()
  public async channelsCreateChannel(
    request: CreateChannelRequest,
  ): Promise<Channel> {
    let media: messages.Media;
    if (request.picture) {
      media = await this.fileToMedia(request.picture);
    }
    const req = new messages.CreateNewsletterRequest({
      session: this.session,
      name: request.name,
      description: request.description,
      picture: media?.content,
    });
    const response = await promisify(this.client.CreateNewsletter)(req);
    const newsletter = response.toObject() as messages.Newsletter;
    return this.toChannel(newsletter);
  }

  @Activity()
  public async previewChannelMessages(
    inviteCode: string,
    query: PreviewChannelMessages,
  ): Promise<ChannelMessage[]> {
    const downloadMedia = query.downloadMedia;
    const request = new messages.GetNewsletterMessagesByInviteRequest({
      session: this.session,
      invite: inviteCode,
      limit: query.limit,
    });
    const response = await promisify(this.client.GetNewsletterMessagesByInvite)(
      request,
    );
    const resp = parseJson(response);
    const promises = [];
    if (!resp.Messages) {
      return [];
    }
    for (const msg of resp.Messages) {
      promises.push(
        this.GowsChannelMessageToChannelMessage(
          resp.NewsletterJID,
          msg,
          downloadMedia,
        ),
      );
    }
    let result = await Promise.all(promises);
    result = result.filter(Boolean);
    return result;
  }

  private async GowsChannelMessageToChannelMessage(
    jid: string,
    channelMessage: any,
    downloadMedia: boolean,
  ): Promise<ChannelMessage> {
    const msg = {
      Info: {
        ID: channelMessage.MessageID,
        ServerID: channelMessage.MessageServerID,
        Chat: jid,
        Sender: jid,
        IsFromMe: false,
        Timestamp: channelMessage.Timestamp,
      },
      Message: channelMessage.Message,
    };
    const message = await this.processIncomingMessage(msg, downloadMedia);
    const reactions: any =
      sortObjectByValues(channelMessage.ReactionCounts) || {};
    return {
      message: message,
      reactions: reactions,
      viewCount: channelMessage.ViewsCount,
    };
  }

  /**
   * Channels Search methods
   */
  @Activity()
  public async searchChannelsByView(
    query: ChannelSearchByView,
  ): Promise<ChannelListResult> {
    const request = new messages.SearchNewslettersByViewRequest({
      session: this.session,
      view: query.view,
      categories: query.categories,
      countries: query.countries,
      page: new messages.SearchPage({
        limit: query.limit,
        startCursor: query.startCursor,
      }),
    });
    const response = await promisify(this.client.SearchNewslettersByView)(
      request,
    );
    return this.channelsRawDataToResponse(response);
  }

  @Activity()
  public async searchChannelsByText(
    query: ChannelSearchByText,
  ): Promise<ChannelListResult> {
    const request = new messages.SearchNewslettersByTextRequest({
      session: this.session,
      text: query.text,
      categories: query.categories,
      page: new messages.SearchPage({
        limit: query.limit,
        startCursor: query.startCursor,
      }),
    });
    const response = await promisify(this.client.SearchNewslettersByText)(
      request,
    );
    return this.channelsRawDataToResponse(response);
  }

  private channelsRawDataToResponse(
    data: messages.NewsletterSearchPageResult,
  ): ChannelListResult {
    const channels: Channel[] = data.newsletters.newsletters.map(
      this.toChannel.bind(this),
    );
    channels.forEach((channel) => {
      delete channel.role;
    });
    return {
      page: {
        startCursor: data.page.startCursor,
        endCursor: data.page.endCursor,
        hasNextPage: data.page.hasNextPage,
        hasPreviousPage: data.page.hasPreviousPage,
      },
      channels: channels,
    };
  }
}
