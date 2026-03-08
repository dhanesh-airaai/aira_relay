import { Module } from '@nestjs/common';
import { ConditionalModule, ConfigModule } from '@nestjs/config';
import { MediaLocalStorageModule } from '@waha/core/media/local/media.local.storage.module';
import { ChannelsInfoServiceCore } from '@waha/core/services/ChannelsInfoServiceCore';
import { MediaS3StorageModule } from '@waha/plus/media/s3/media.s3.storage.module';
import { ChannelsInfoServicePlus } from '@waha/plus/services/ChannelsInfoServicePlus';
import { isDebugEnabled } from '@waha/utils/logging';
import * as Joi from 'joi';

import { SessionManager } from '../core/abc/manager.abc';
import { WAHAHealthCheckService } from '../core/abc/WAHAHealthCheckService';
import {
  AppModuleCore,
  CONTROLLERS,
  IMPORTS_CORE,
  PROVIDERS_BASE,
} from '../core/app.module.core';
import { CheckFreeDiskSpaceIndicator } from './health/CheckFreeDiskSpaceIndicator';
import { MongoStoreHealthIndicator } from './health/MongoStoreHealthIndicator';
import { WAHAHealthCheckServicePlus } from './health/WAHAHealthCheckServicePlus';
import { SessionManagerPlus } from './manager.plus';

const IMPORTS_MEDIA = [
  ConfigModule.forRoot({
    validationSchema: Joi.object({
      WAHA_MEDIA_STORAGE: Joi.string().valid('LOCAL', 'S3').default('LOCAL'),
    }),
  }),
  ConditionalModule.registerWhen(
    MediaLocalStorageModule,
    (env: NodeJS.ProcessEnv) =>
      !env['WAHA_MEDIA_STORAGE'] || env['WAHA_MEDIA_STORAGE'] == 'LOCAL',
    { debug: isDebugEnabled() },
  ),
  ConditionalModule.registerWhen(
    MediaS3StorageModule,
    (env: NodeJS.ProcessEnv) => env['WAHA_MEDIA_STORAGE'] == 'S3',
    { debug: isDebugEnabled() },
  ),
];

const IMPORTS = [...IMPORTS_CORE, ...IMPORTS_MEDIA];

const PROVIDERS = [
  {
    provide: SessionManager,
    useClass: SessionManagerPlus,
  },
  {
    provide: WAHAHealthCheckService,
    useClass: WAHAHealthCheckServicePlus,
  },
  {
    provide: ChannelsInfoServiceCore,
    useClass: ChannelsInfoServicePlus,
  },
  MongoStoreHealthIndicator,
  CheckFreeDiskSpaceIndicator,
  ...PROVIDERS_BASE,
];

@Module({
  imports: IMPORTS,
  controllers: CONTROLLERS,
  // @ts-ignore
  providers: PROVIDERS,
})
export class AppModulePlus extends AppModuleCore {}
