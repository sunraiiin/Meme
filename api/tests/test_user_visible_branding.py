import unittest
from pathlib import Path
from unittest.mock import patch

from app.controllers.health_controller import hello
from app.main import create_app


class UserVisibleBrandingTests(unittest.IsolatedAsyncioTestCase):
    async def test_hello_uses_meme_branding(self):
        with patch("app.controllers.health_controller.settings.app_name", "Meme"):
            result = await hello()

        self.assertEqual(result["data"], {"app": "Meme", "message": "你好，Meme"})

    def test_openapi_description_uses_meme_branding(self):
        with patch("app.main.settings.app_name", "Meme"):
            app = create_app()

        self.assertEqual(app.description, "Meme — 个人 AI 知识库与记忆助手")

    def test_react_prompt_uses_meme_branding(self):
        prompt_path = (
            Path(__file__).parents[1]
            / "app"
            / "core"
            / "agent"
            / "prompts"
            / "react.jinja2"
        )

        prompt = prompt_path.read_text(encoding="utf-8")
        self.assertIn("你是「Meme」的智能助手", prompt)
        self.assertNotIn("你是「彗记」的智能助手", prompt)


if __name__ == "__main__":
    unittest.main()
