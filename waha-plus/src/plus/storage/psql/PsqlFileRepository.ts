import Knex from 'knex';
import { Logger } from 'pino';

function Migrations(table: string): string[] {
  return [
    `CREATE TABLE IF NOT EXISTS ${table}
     (
         id               SERIAL PRIMARY KEY,
         fullpath         TEXT  NOT NULL,
         content          BYTEA NOT NULL,
         created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         last_accessed_at TIMESTAMP DEFAULT NULL,
         metadata         JSONB
     )`,
    // fullpath is unique constraint
    `CREATE UNIQUE INDEX IF NOT EXISTS ${table}_fullpath_index ON ${table} (fullpath)`,
    // index on created
    `CREATE INDEX IF NOT EXISTS ${table}_created_at_index ON ${table} (created_at)`,
    // index on last_accessed_at
    `CREATE INDEX IF NOT EXISTS ${table}_last_accessed_at_index ON ${table} (last_accessed_at)`,
    // index on metadata (JSONB)
    `CREATE INDEX IF NOT EXISTS ${table}_metadata_index ON ${table} USING GIN (metadata)`,
  ];
}

export interface FileData {
  fullpath: string;
  content: Buffer;
  created_at: number;
  metadata: any;
}

/**
 * General purpose file repository for storing files in a PostgreSQL database.
 */
export class PsqlFileRepository {
  get tableName() {
    return 'files';
  }

  constructor(
    private knex: Knex.Knex,
    private logger: Logger,
  ) {}

  protected table() {
    return this.knex(this.tableName);
  }

  async save(fullpath: string, content: Buffer, metadata: any = {}) {
    const now = new Date().toISOString();
    await this.table()
      .insert({
        fullpath: fullpath,
        content: content,
        created_at: now,
        metadata: metadata,
      })
      .onConflict('fullpath')
      .merge({
        content: this.knex.raw('EXCLUDED.content'),
        created_at: this.knex.raw('EXCLUDED.created_at'),
        metadata: this.knex.raw('EXCLUDED.metadata'),
      });
  }

  async exists(fullpath: string): Promise<boolean> {
    const result = await this.table().where('fullpath', fullpath);
    return result.length > 0;
  }

  async delete(fullpath: string) {
    await this.table().where('fullpath', fullpath).del();
  }

  async fetch(fullpath: string): Promise<FileData | null> {
    const result = await this.table().where('fullpath', fullpath);
    const data = result.length > 0 ? result[0] : null;
    if (!data) {
      return null;
    }
    data.created_at = new Date(data.created_at).getTime();
    this.touch(fullpath).catch((err) => {
      this.logger.error(`Failed to save last accessed time: ${err}`);
    });
    return data;
  }

  async init() {
    for (const migration of this.migrations()) await this.knex.raw(migration);
  }

  protected async touch(fullpath: string) {
    const now = new Date().toISOString();
    await this.table()
      .where('fullpath', fullpath)
      .update({ last_accessed_at: now });
  }

  protected migrations() {
    return Migrations(this.tableName);
  }
}
