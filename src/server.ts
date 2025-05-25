import express from 'express';
import cors from 'cors';
import dotenv from 'dotenv';
import topicsRouter from './routes/topics';

dotenv.config();

const app = express();
const port = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());

// ルートの設定
app.use('/api/topics', topicsRouter);

app.get('/', (req, res) => {
  res.json({ message: 'Welcome to Recomate API' });
});

app.listen(port, () => {
  console.log(`Server is running on port ${port}`);
}); 