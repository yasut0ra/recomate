import express from 'express';
import { Router } from 'express';

const router: Router = express.Router();

// トピック一覧の取得
router.get('/', (req, res) => {
  res.json({ message: 'Get all topics' });
});

// 特定のトピックの取得
router.get('/:id', (req, res) => {
  res.json({ message: `Get topic with id: ${req.params.id}` });
});

// トピックの作成
router.post('/', (req, res) => {
  res.json({ message: 'Create new topic' });
});

// トピックの更新
router.put('/:id', (req, res) => {
  res.json({ message: `Update topic with id: ${req.params.id}` });
});

// トピックの削除
router.delete('/:id', (req, res) => {
  res.json({ message: `Delete topic with id: ${req.params.id}` });
});

export default router; 