import { DataStore } from '@waha/core/abc/DataStore';
import { GowsAuth } from '@waha/core/engines/gows/store/GowsAuth';
import { GowsAuthFactoryCore } from '@waha/core/engines/gows/store/GowsAuthFactoryCore';
import { GowsAuthSimple } from '@waha/core/engines/gows/store/GowsAuthSimple';
import { MongoStore } from '@waha/plus/storage/mongo/MongoStore';

export class GowsAuthFactoryPlus extends GowsAuthFactoryCore {
  buildAuth(store: DataStore, name: string): Promise<GowsAuth> {
    if (store instanceof MongoStore) return this.buildMongo(store, name);
    return super.buildAuth(store, name);
  }

  /**
   * Build GowsAuth using the GOWS MongoDB store.
   * Passes dialect="mongodb" and the per-session MongoDB URL to the Go service,
   * which is handled by the mongostore package in GOWS.
   */
  async buildMongo(store: MongoStore, name: string): Promise<GowsAuth> {
    const connection = store.getSessionDbURL(name);
    return new GowsAuthSimple(connection, 'mongodb');
  }
}
