import pygame
import os
import numpy as np

class VtuberModel:
    def __init__(self):
        # Pygameの初期化
        pygame.init()
        self.screen = pygame.display.set_mode((800, 600))
        pygame.display.set_caption("Vtuber AI")
        self.clock = pygame.time.Clock()

        # フォントの初期化
        self.font = pygame.font.Font(None, 36)

        # 画像の読み込み
        self.base_image = pygame.image.load('characters/base.png')
        self.expressions = {
            'neutral': pygame.image.load('characters/expressions/neutral.png'),
            'happy': pygame.image.load('characters/expressions/happy.png'),
            'sad': pygame.image.load('characters/expressions/sad.png'),
            'angry': pygame.image.load('characters/expressions/angry.png'),
            'surprised': pygame.image.load('characters/expressions/surprised.png')
        }

        # 現在の表情
        self.current_expression = 'neutral'
        
        # アニメーション用の変数
        self.mouth_open = 0.0  # 0.0から1.0の間で口の開き具合を制御
        self.blink_timer = 0
        self.is_blinking = False

    def update(self, emotion=None, is_speaking=False):
        # 感情に基づいて表情を更新
        if emotion and emotion in self.expressions:
            self.current_expression = emotion
            print(f"表情を {emotion} に変更しました")  # デバッグ用

        # 口パクアニメーション
        if is_speaking:
            self.mouth_open = (self.mouth_open + 0.1) % 1.0
        else:
            self.mouth_open = 0.0

        # まばたきアニメーション
        self.blink_timer += 1
        if self.blink_timer >= 180:  # 約3秒ごとにまばたき
            self.is_blinking = True
            self.blink_timer = 0
        elif self.blink_timer >= 5:  # まばたきは5フレームで完了
            self.is_blinking = False

    def update_expression(self, expression_data: str):
        """感情表現を更新"""
        try:
            # 表情の説明から適切な表情を選択
            if "笑顔" in expression_data or "喜び" in expression_data:
                self.current_expression = 'happy'
            elif "悲しい" in expression_data or "泣き" in expression_data:
                self.current_expression = 'sad'
            elif "怒り" in expression_data or "不満" in expression_data:
                self.current_expression = 'angry'
            elif "驚き" in expression_data or "びっくり" in expression_data:
                self.current_expression = 'surprised'
            else:
                self.current_expression = 'neutral'
            
            print(f"表情を {self.current_expression} に変更しました")
            
            # 音声の調子に応じて口パクの速度を調整
            if "高い声" in expression_data:
                self.mouth_open = 0.8
            elif "低い声" in expression_data:
                self.mouth_open = 0.3
            else:
                self.mouth_open = 0.5
                
        except Exception as e:
            print(f"表情の更新でエラーが発生: {e}")
            self.current_expression = 'neutral'

    def render(self):
        # 画面のクリア
        self.screen.fill((128, 128, 128))

        # 基本画像の描画
        self.screen.blit(self.base_image, (200, 100))

        # 表情の描画
        expression_image = self.expressions[self.current_expression]
        self.screen.blit(expression_image, (200, 100))

        # デバッグ情報の表示
        debug_text = f"現在の表情: {self.current_expression}"
        text_surface = self.font.render(debug_text, True, (255, 255, 255))
        self.screen.blit(text_surface, (10, 10))

        # 口パクアニメーションの描画（必要に応じて実装）
        if self.mouth_open > 0:
            # 口パク用の画像や処理をここに追加
            pass

        # まばたきの描画
        if self.is_blinking:
            # まばたき用の画像や処理をここに追加
            pass

        pygame.display.flip()
        self.clock.tick(60)

    def cleanup(self):
        pygame.quit() 