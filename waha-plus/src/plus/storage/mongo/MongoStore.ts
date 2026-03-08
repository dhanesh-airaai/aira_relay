import { Document } from 'bson';
import Knex from 'knex';
import { MongoClient } from 'mongodb';

import { DataStore } from '../../../core/abc/DataStore';

export class MongoStore extends DataStore {
  private mongo: MongoClient;
  private engine: string;
  private mongoUrl: string;

  constructor(mongo: MongoClient, engine: string, mongoUrl?: string) {
    super();
    if (!mongo)
      throw new Error(
        'A valid MongoClient instance is required for MongoStore.',
      );
    this.mongo = mongo;
    this.engine = engine.toLowerCase();
    this.mongoUrl = mongoUrl || '';
  }

  protected getMainDbName() {
    return `waha_${this.engine.toLowerCase()}`;
  }

  protected getSessionDbName(name: string) {
    const slug = name.toLowerCase().replace(/[^a-z0-9-]/g, '_');
    return `${this.getMainDbName()}_${slug}`;
  }

  getMainDb() {
    return this.mongo.db(this.getMainDbName());
  }

  getSessionDb(name: string) {
    return this.mongo.db(this.getSessionDbName(name));
  }

  /**
   * Returns a MongoDB connection URL pointing to the per-session database.
   * Used by GowsAuthFactoryPlus to tell the GOWS Go service which MongoDB
   * database to use for its whatsmeow session store.
   *
   * Example: mongodb://user:pass@host:27017/waha_gows_mysession
   */
  getSessionDbURL(name: string): string {
    const dbName = this.getSessionDbName(name);
    if (!this.mongoUrl) {
      throw new Error(
        'MongoStore was created without a mongoUrl; cannot build session DB URL.',
      );
    }
    // Replace or append the database name in the URL path
    // mongodb://user:pass@host:27017[/existing_db][?options]
    try {
      const url = new URL(this.mongoUrl);
      url.pathname = `/${dbName}`;
      return url.toString();
    } catch {
      // Fallback: naive string replacement
      return this.mongoUrl.replace(/\/[^/?]+(\?|$)/, `/${dbName}$1`);
    }
  }

  command(command: Document) {
    return this.mongo.db().admin().command(command);
  }

  async init(sessionName?: string): Promise<void> {
    if (!sessionName) {
      const collection = this.getMainDb().collection('sessions');
      await collection.createIndex({ name: 1 }, { unique: true });
    }
  }

  async close() {
    await this.mongo?.close();
  }

  getWAHADatabase(): Knex.Knex {
    throw new Error(
      'WAHA SQL database is not available for Mongo-backed session storage.',
    );
  }
}
