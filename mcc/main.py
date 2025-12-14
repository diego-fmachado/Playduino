from src.app import main
from asyncio import run
from machine import soft_reset

run(main())
soft_reset()