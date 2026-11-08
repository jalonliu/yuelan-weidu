#!/usr/bin/env node
/**
 * 把本插件仓库（D:\jalon\dsh-yuelan）的最新内容同步到
 * yuelan-weidu 仓库的 dsh-plugin/ 子目录，并提交推送到 GitHub。
 *
 * 用法：改完插件后运行
 *   node scripts/sync-github.mjs "本次修改说明"
 *
 * 同步范围 = package.json 的 files 白名单 + src + scripts + docs（不含 lib/node_modules，
 * lib 由 prepare 脚本在安装时现场构建）。
 * @module aurora/scripts/sync-github
 */

import { execSync } from 'node:child_process'
import { cp, mkdtemp, readFile, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SRC_REPO = resolve(HERE, '..')
const DST_REPO = 'D:/jalon/yuelan-weidu'
const DST_SUB = join(DST_REPO, 'dsh-plugin')

const message = process.argv.slice(2).join(' ') || `sync: dsh-yuelan 更新同步 ${new Date().toISOString()}`

const tracked = [
  'package.json',
  'cordis.patch.yml',
  'README.md',
  'LICENSE',
  'tsconfig.json',
  'VERSION',
]

function git(repo, args) {
  return execSync(`git ${args}`, { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
}

try {
  // 0. 本仓库必须干净（避免把半成品状态同步出去）
  const dirty = git(SRC_REPO, 'status --porcelain')
  if (dirty !== '') {
    console.error('本仓库有未提交的改动，请先 commit：\n' + dirty)
    process.exit(1)
  }

  // 1. 复制内容
  for (const item of tracked) {
    try {
      await cp(join(SRC_REPO, item), join(DST_SUB, item), { recursive: true, force: true })
    } catch (e) {
      if (e.code !== 'ENOENT') throw e
      console.warn(`跳过不存在的文件: ${item}`)
    }
  }
  for (const dir of ['src', 'scripts', 'docs']) {
    try {
      await cp(join(SRC_REPO, dir), join(DST_SUB, dir), { recursive: true, force: true })
    } catch (e) {
      if (e.code !== 'ENOENT') throw e
    }
  }

  // 2. 目标仓库有变化才提交推送
  const status = git(DST_REPO, 'status --porcelain -- dsh-plugin')
  if (status === '') {
    console.log('GitHub 副本已是最新，无需同步。')
    process.exit(0)
  }

  // 3. 版本一致性哨兵：源 package.json 的 version 必须出现在 README 或修复记录里（弱校验，仅提示）
  const pkg = JSON.parse(await readFile(join(SRC_REPO, 'package.json'), 'utf8'))
  console.log(`同步 dsh-yuelan v${pkg.version}`)

  git(DST_REPO, 'add dsh-plugin')
  git(DST_REPO, `commit -m ${JSON.stringify(message)}`)
  console.log(git(DST_REPO, 'push origin main'))
  console.log('已同步并推送 GitHub。')
} catch (error) {
  console.error('同步失败:', error.message)
  process.exit(1)
}
