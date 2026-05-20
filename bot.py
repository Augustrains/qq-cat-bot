from dotenv import load_dotenv
load_dotenv("/home/ubuntu/robot/.env")

import nonebot
from nonebot.adapters.qq import Adapter as QQAdapter

nonebot.init()

driver = nonebot.get_driver()
driver.register_adapter(QQAdapter)

nonebot.load_plugins("plugins")

if __name__ == "__main__":
    nonebot.run()
