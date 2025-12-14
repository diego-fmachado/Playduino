from machine import Pin
from neopixel import NeoPixel
from report import ErrorReporter
from random import shuffle
from random import randint
from asyncio import create_task
from asyncio import Event
from asyncio import sleep_ms
from time import ticks_ms
from math import ceil
from itertools import dropwhile
from itertools import islice
from itertools import chain_from_iterable
from itertools import cycle
from operator import lt
from operator import ge
from contextlib import contextmanager
from typing import Iterable
from typing import Optional
from typing import Sequence
from typing import Union
from typing import Callable
from typing import Any
from typing import Self

from sys import maxsize
import gc

LED_PIN = 4

class EngineError(RuntimeError): ...
class SpawnError(EngineError): ...

def init_class[C: type](cls: C):
    init: Callable[[], None] | None = getattr(cls, "__init_class__", None)
    if init:
        assert isinstance(cls.__dict__[init.__name__], classmethod), \
            "__init_class__ has to be a classmethod"
        init()
    return cls

type Coord = tuple[int, int]

class COPS():
    @staticmethod
    def add(a: Coord, b: Coord):
        return a[0] + b[0], a[1] + b[1]
    
    @staticmethod
    def sub(a: Coord, b: Coord):
        return a[0] - b[0], a[1] - b[1]
    
    @staticmethod
    def mul(a: Coord, b: Coord):
        return a[0] * b[0], a[1] * b[1]
    
    @staticmethod
    def div(a: Coord, b: Coord):
        return a[0] // b[0], a[1] // b[1]

class Copyable():
    def copy(self, other: 'Copyable'):
        for name in other.__dict__:
            setattr(self, name, getattr(other, name))

class BlockAngles():
    (
        DEG_0,
        DEG_90,
        DEG_180,
        DEG_270,
    ) = range(4)

type OrtFilters = list[Callable[[Coord], Coord]]

class Cached():
    _cache: dict[type['Cached'], list[Self]] = {}
    _cache_i: int

    @classmethod
    def new_empty(cls):
        return object.__new__(cls)
    
    @classmethod
    def _get_cache(cls):
        try:
            return cls._cache[cls]
        except KeyError:
            return cls._cache.setdefault(cls, [])

    @classmethod
    def _get_cached(cls):
        cls._cache_i += 1
        cache = cls._get_cache()
        try:
            return cache[cls._cache_i]
        except IndexError:
            pos = cls.new_empty()
            cache.append(pos)
            return pos

    @classmethod
    @contextmanager
    def _enable_cache(cls):
        cls._cache_i = -1
        try:
            yield
        finally:
            delattr(cls, "_cache_i")

    
class BlockPos(Copyable, Cached):
    _ORT_FILTERS: OrtFilters = [
        lambda c: c,
        lambda c: (-c[1], c[0]),
        lambda c: (-c[0], -c[1]),
        lambda c: (c[1], -c[0])
    ]
    _ORT_REVERSE_FILTERS: OrtFilters = [
        lambda c: c,
        lambda c: (c[1], -c[0]),
        lambda c: (-c[0], -c[1]),
        lambda c: (-c[1], c[0])
    ]

    def __init__(
        self,
        ref: Coord,
        offs: tuple[Coord],
        ort_i: int
    ):
        self.offs = offs
        self.ref = ref
        self.ort_i = ort_i

    def __iter__(self):
        ort_filter = self._ORT_FILTERS[self.ort_i % 4]
        for off in self.offs:
            yield COPS.add(self.ref, ort_filter(off))

    def to_offset(self, coord: Coord):
        ort_filter = self._ORT_REVERSE_FILTERS[self.ort_i % 4]
        return ort_filter(COPS.sub(coord, self.ref))

    def remove(self, coord: Coord):
        off = self.to_offset(coord)
        self.offs = tuple(off_ for off_ in self.offs if off_ != off)

    def has_cells(self):
        return bool(self.offs)
    
    def __repr__(self):
        return str(self.__dict__)

class BlockMove():
    _i: int

    def _apply(self, pos: BlockPos):
        raise NotImplementedError

    def _revert(self, pos: BlockPos):
        raise NotImplementedError


class MissingMoveError(Exception): ...

class BlockShift(BlockMove):
    _i = 0
    _ORIGIN = 0, 0

    def __init__(self, shift: Coord):
        self._shift = shift

    def __mul__(self, other: 'BlockShift'):
        return BlockShift(COPS.mul(self._shift, other._shift))
        
    def _apply(self, pos):
        pos.ref = COPS.add(pos.ref, self._shift)

    def _simulate(self, coord: Coord):
        return COPS.add(self._shift, coord)

    def _revert(self, pos):
        pos.ref = COPS.sub(pos.ref, self._shift)

    def _is_opposite(self, other: 'BlockShift'):
        return COPS.add(self._shift, other._shift) == self._ORIGIN
    
class BlockRotate(BlockMove):
    _i = 1

    def __init__(self, factor: int):
        self._factor = factor

    def _apply(self, pos):
        pos.ort_i += self._factor

    def _revert(self, pos):
        pos.ort_i -= self._factor

class SpawnDirective(): ...

type DirectiveGetter = Callable[[type[GameBlock]], int]

@init_class
class SpawnDirectives():
    START = SpawnDirective()
    END = SpawnDirective()
    CENTER = SpawnDirective()
    RANDOM = SpawnDirective()

    @classmethod
    def __init_class__(cls):
        zero_getter = lambda _: 0
        start: list[DirectiveGetter] = [
            zero_getter,
            zero_getter,
            lambda b: b._height - 1,
            zero_getter,
            lambda b: b._width - 1,
            lambda b: b._height - 1,
            zero_getter,
            lambda b: b._width - 1
        ]
        end: list[DirectiveGetter] = [
            lambda b: ScreenInfo.WIDTH - b._width,
            lambda b: ScreenInfo.HEIGHT - b._height,
            lambda _: ScreenInfo.WIDTH - 1,
            lambda b: ScreenInfo.HEIGHT - b._width,
            lambda _: ScreenInfo.WIDTH - 1,
            lambda _: ScreenInfo.HEIGHT - 1,
            lambda b: ScreenInfo.WIDTH - b._height,
            lambda _: ScreenInfo.HEIGHT - 1,
        ]
        center: list[DirectiveGetter] = [
            lambda b: ScreenInfo.WIDTH // 2 - b._width // 2,
            lambda b: ScreenInfo.HEIGHT // 2 - b._height // 2,
            lambda b: ScreenInfo.WIDTH // 2 + b._height // 2,
            lambda b: ScreenInfo.HEIGHT // 2 - b._width // 2,
            lambda b: ScreenInfo.WIDTH // 2 + b._width // 2,
            lambda b: ScreenInfo.HEIGHT // 2 + b._height // 2,
            lambda b: ScreenInfo.WIDTH // 2 - b._height // 2,
            lambda b: ScreenInfo.HEIGHT // 2 + b._width // 2
        ]

        def get_random_getter(i: int) -> DirectiveGetter:
            return lambda b: randint(start[i](b), end[i](b))

        cls._getter_map: dict[SpawnDirective, list[DirectiveGetter]] = {
            cls.START: start,
            cls.END: end,
            cls.CENTER: center,
            cls.RANDOM: list(map(get_random_getter, range(8)))
        }

class BlockMoves():
    SHIFT_LEFT = BlockShift((-1, 0))
    SHIFT_RIGHT = BlockShift((1, 0))
    SHIFT_UP = BlockShift((0, -1))
    SHIFT_DOWN = BlockShift((0, 1))
    SHIFT_UP_LEFT = BlockShift((-1, -1))
    SHIFT_UP_RIGHT = BlockShift((1, -1))
    SHIFT_DOWN_LEFT = BlockShift((-1, 1))
    SHIFT_DOWN_RIGHT = BlockShift((1, 1))
    ROTATE_CW = BlockRotate(1)
    ROTATE_CCW = BlockRotate(-1)

class ScreenInfo():
    WIDTH = HEIGHT = 16
    REFRESH_RATE = 60

class WallCorner(): ...
class VerticalCorner(WallCorner): ...
class HorizontalCorner(WallCorner): ...

def add(a: int, b: int):
    return a + b

def sub(a: int, b: int):
    return a - b

class WallCorners(Cached):
    _cache_i = -1

    TOP = VerticalCorner()
    BOTTOM = VerticalCorner()
    LEFT = HorizontalCorner()
    RIGHT = HorizontalCorner()

    def __init__(self, corners: list[WallCorner]):
        self._corners = corners

    def __contains__(self, corner: type[WallCorner] | WallCorner):
        if not type(corner) is type:
            return corner in self._corners
        return any(
            isinstance(corner_, corner)
            for corner_ in self._corners
        )
    
    def __iter__(self):
        return iter(self._corners)

BOUNDING_CORNERS = (
    WallCorners.LEFT,
    WallCorners.TOP,
    WallCorners.RIGHT,
    WallCorners.BOTTOM
)

class GameBlock():
    color: tuple[int, int, int] = 255, 255, 255
    shape: Optional[list[list[int]]] = None
    cross_corners: list[WallCorner] = []
    _MME = MissingMoveError()
    _max_length = 0

    @classmethod
    def _process(cls):
        def is_empty_row(row: list[int]):
            return not any(row)
        
        def get_offsets():
            start_x = min(
                next(
                    (x for x, cell in enumerate(row) if cell),
                    ScreenInfo.WIDTH
                )
                for row in cls.shape
            )
            offsets = tuple(
                (x, y)
                for y, row in enumerate(
                    islice(
                        dropwhile(
                            is_empty_row,
                            cls.shape
                        ),
                        ScreenInfo.HEIGHT
                    )
                )
                for x, cell in enumerate(
                    islice(row, start_x, ScreenInfo.WIDTH)
                )
                if cell
            )
            if not offsets:
                raise EngineError(
                    "There are no active "
                    "cells in block's shape"
                )
            return offsets
        
        if not cls.shape:
            raise EngineError(
                "You must define shape "
                "by overloading the class variable"
            )
        cls._offsets = get_offsets()
        cls._width = max(coord[0] for coord in cls._offsets) + 1
        cls._height = max(coord[1] for coord in cls._offsets) + 1
        GameBlock._max_length = max(
            GameBlock._max_length,
            cls._width,
            cls._height
        )
        cls._acronym = "".join(
            char
            for char in cls.__name__
            if char.isupper() or char.isdigit()
        )

    @classmethod
    def _post_process(cls):
        def get_boundings():
            for i, corner in enumerate(BOUNDING_CORNERS):
                half = i // 2
                yield (
                    (half and bases[i % 2] or 0) +
                    half * cls._max_length +
                    ((corner not in cls.cross_corners) ^ half) * cls._max_length 
                )

        bases = ScreenInfo.WIDTH, ScreenInfo.HEIGHT
        cls._boundings = tuple(get_boundings())

    def is_fully_visible(self):
        max_length = self._max_length
        dimensions = ScreenInfo.WIDTH, ScreenInfo.HEIGHT
        return all(
            c >= max_length and c < dim + max_length
            for coord in self._pos
            for c, dim in zip(coord, dimensions)
        )

    def __init__(self):
        self._pos = BlockPos.new_empty()
        self._move_slots: list[BlockMove | None] = [None, None]

    def _abort_move(self, move_type: type[BlockMove]):
        self._move_slots[move_type._i] = None

    def _wants_to_move(self, move_type: type[BlockMove]):
        return bool(self._move_slots[move_type._i])

    def _get_move[C: BlockMove](self, move_type: type[C]) -> C:
        move = self._move_slots[move_type._i]
        if not move:
            raise self._MME
        return move
        
    def move(self, block_move: BlockMove):
        self._move_slots[block_move._i] = block_move

    def on_spawn(self): ...

    def on_collision(
        self,
        other: Union['WallCorners', 'GameBlock'],
        engine: 'GameEngine',
        move: BlockMove
    ):
        ...

    def on_transposition(self, engine: 'GameEngine'): ...

    @property
    def ref(self):
        return self._pos.ref
    
    @property
    def width(self):
        return self._width
    
    @property
    def height(self):
        return self._height
    
    @classmethod
    def get_max_length(cls):
        return cls._max_length

    def __repr__(self):
        return self._acronym

class ValuedException[T](Exception):
    def set_and_raise(self, value: T):
        self.value = value
        raise self

class BlockConflictError(ValuedException[Sequence[GameBlock]]): ...
class GameGridError(Exception): ...
class MissingBlockError(Exception): ...
class OutOfBoundsError(ValuedException[WallCorners]): ...
    
class Matrix[T]():
    @staticmethod
    def _new_cell(_) -> T: ...

    def __init__(self, border_size: int=0):
        self._matrix = self._new_matrix(border_size)

    @classmethod
    def _new_matrix(cls, border_size: int) -> tuple[Sequence[T]]:
        row_cls = tuple if cls._is_cell_mutable() else list
        extra_size = border_size * 2
        return tuple(
            row_cls(
                cls._new_cell((x, y))
                for x in range(ScreenInfo.WIDTH + extra_size)
            )
            for y in range(ScreenInfo.HEIGHT + extra_size)
        )
    
    def get_row(self, index: int):
        return self._matrix[index]
    
    @classmethod
    def _is_cell_mutable(cls):
        return cls.__setitem__ is Matrix.__setitem__
    
    def __setitem__(*_):
        raise EngineError(
            "The cell is mutable by default, "
            "thus you can't replace it"
        )
    
    def __getitem__(self, coord: Coord):
        return self._matrix[coord[1]][coord[0]]

    def __iter__(self):
        return iter(self._matrix)
    
    @staticmethod
    def _clear_row(_):
        raise NotImplementedError

    def clear(self):
        for row in self._matrix:
            self._clear_row(row)
    
class MissingBlockError(EngineError): ...

class GridSlot():
    _MBE = MissingBlockError()

    def __init__(self, coord: Coord):
        self._coord = coord
        self._slot: list[GameBlock] = []

    def __iter__(self):
        return iter(self._slot)

    def clear(self):
        self._slot.clear()

    def remove(self, block: GameBlock):
        try:
            return self._slot.remove(block)
        except ValueError:
            raise self._MBE
        
    def add(self, block: GameBlock):
        self._slot.append(block)
    
    def flush(self):
        try:
            while True:
                yield self._slot.pop()
        except IndexError:
            pass
    
    @property
    def front(self):
        try:
            return self._slot[0]
        except IndexError:
            raise self._MBE
        
        
    def __bool__(self):
        return bool(self._slot)

    def __contains__(self, block: GameBlock):
        return block in self._slot

    def __len__(self):
        return len(self._slot)
    
class RevertedBlockError(Exception): ...

class PixelColors:
    RED = 255, 0, 0  
    GREEN = 0, 255, 0   
    BLUE = 0, 0, 255 
    CYAN = 0, 255, 255 
    MAGENTA = 255, 0, 255
    YELLOW = 255, 255, 0   
    ORANGE = 255, 128, 0 
    PURPLE = 128, 0, 255 
    PINK = 255, 64, 192
    LIGHT_BLUE = 64, 200, 255
    LIME = 180, 255, 0
    TEAL = 0, 180, 180
    GRAY = 128, 128, 128
    OFF = 0, 0, 0


class GameLoop():
    def __init__(self):
        self._i: int = 0
        self._is_stopping: bool = False
        self._last_iter_ms: int = 0
        self._sleep_ms: int = ceil(1 / ScreenInfo.REFRESH_RATE * 1000)
        self._delta_collect = ScreenInfo.REFRESH_RATE

    @property
    def i(self):
        return self._i

    def stop(self):
        self._is_stopping = True

    def __aiter__(self):
        return self
    
    async def __anext__(self):
        if self._is_stopping:
            raise StopAsyncIteration
        sleep_discount = ticks_ms() - self._last_iter_ms
        sleep_duration = max(self._sleep_ms - sleep_discount, 0)
        await sleep_ms(sleep_duration)
        self._last_iter_ms = ticks_ms()
        self._i += 1
        if self._i % self._delta_collect == 0:
            # gc.collect()
            print(gc.mem_free())

class ScreenLayer(Matrix[tuple[int, int, int] | None]):
    _row_filters = iter, reversed
    
    def __setitem__(
        self,
        coord: Coord,
        pixel: tuple[int, int, int] | None
    ):
        self._matrix[coord[1]][coord[0]] = pixel

    @staticmethod
    def _clear_row(row):
        for i in range(len(row)):
            row[i] = None

    def fill_with(self, pixel: tuple[int, int, int]):
        for row in self._matrix:
            for i in range(len(row)):
                row[i] = pixel
    
    def __iter__(self):
        for row, row_filter in zip(
            self._matrix,
            cycle(self._row_filters)
        ):
            yield from row_filter(row)

class ScreenRenderer():
    def __init__(self):
        self._layers: list[ScreenLayer] = []
        self._neopixel = NeoPixel(
            Pin(LED_PIN),
            ScreenInfo.WIDTH * ScreenInfo.HEIGHT
        )

    def new_layer(self) -> ScreenLayer:
        layer = ScreenLayer()
        self._layers.append(layer)
        return layer
    
    @classmethod
    def _choose_pixel(cls, pixels: tuple[tuple[int, int, int] | None]):
        for pixel in pixels:
            if pixel:
                return pixel
        return PixelColors.OFF
    
    def _get_pixel_values(self):
        return map(self._choose_pixel, zip(*self._layers))
    
    def render(self):
        for i, pixel in enumerate(self._get_pixel_values()):
            self._neopixel[i] = pixel
        self._neopixel.write()

class AnimationDoneError(Exception): ...

class GameAnimation():
    _n_stages: int
    _stage_duration: int
    _ADE = AnimationDoneError()

    def __init__(self, loop: GameLoop, renderer: ScreenRenderer):
        self._loop = loop
        self._layer = renderer.new_layer()
        self._is_active = False
        self._post_init()
    
    def _post_init(self): ...

    def _on_stage_switch(self, n_stage: int): ...

    def _activate(self):
        self._is_active = True

    def _deactivate(self):
        self._is_active = False
        self._layer.clear()

    def run(self):
        if self._is_active:
            if self._loop.i % self._stage_duration == 0:
                self._on_stage_switch(
                    self._loop.i //
                    self._stage_duration %
                    self._n_stages
                )
            raise self._ADE

class BlockBlinker(GameAnimation):
    _stage_duration = 2
    _n_stages = 2
    
    def _post_init(self):
        self._n_blinks = 0
        self._coords: list[Coord] = []

    def _deactivate(self):
        super()._deactivate()
        self._n_blinks = 0
        self._coords.clear()

    def add_coordinate(self, coord: Coord):
        self._activate()
        max_length = GameBlock._max_length
        if coord[0] >= max_length and coord[1] >= max_length:
            coord = coord[0] - max_length, coord[1] - max_length
            self._coords.append(coord)
    
    def _on_stage_switch(self, n_stage):
        pixel_off = PixelColors.OFF #Caching...
        if n_stage:
            for coord in self._coords:
                self._layer[coord] = pixel_off
            self._n_blinks += 1
            if self._n_blinks > 12:
                self._deactivate()
        else:
            self._layer.clear()

class BlinkingXOnError(GameAnimation):
    _stage_duration = ScreenInfo.REFRESH_RATE
    _n_stages = 2
    _x_coords = tuple(
        (x, y)
        for y in range(ScreenInfo.HEIGHT)
        for x in range(ScreenInfo.WIDTH)
        if x == y or x + y == ScreenInfo.WIDTH - 1
    )
        
    def activate(self):
        self._activate()

    def _on_stage_switch(self, n_stage):
        if n_stage:
            self._layer.fill_with(PixelColors.OFF)
            for coord in self._x_coords:
                self._layer[coord] = PixelColors.RED
        else:
            self._layer.clear()

class Animator():
    def __init__(
        self,
        animations: dict[type[GameAnimation], GameAnimation]
    ):
        self._animations = animations

    @classmethod
    def new(
        cls,
        loop: GameLoop,
        renderer: ScreenRenderer,
        *animation_classes: type[GameAnimation]
    ):
        animations = dict(
            (animation_cls, animation_cls(loop, renderer))
            for animation_cls in animation_classes
        )
        return cls(animations)
    
    def get[C: GameAnimation](self, animation_cls: type[C]) -> C:
        return self._animations[animation_cls]
    
    def __enter__(self):
        return self._run
    
    def __exit__(self, exc_type: type[Exception] | None, *_):
        return exc_type is AnimationDoneError

    def _run(self):
        for animation in self._animations.values():
            animation.run()



class BlockPool():
    def __init__(self):
        self._cache: dict[type[GameBlock], list[GameBlock]] = {}
        self._pool = set[GameBlock]()
        self._to_remove = set[GameBlock]()
        self._to_add: list[GameBlock] = []

    def __iter__(self):
        return iter(self._pool)
    
    def _get_cache(self, block_type: type[GameBlock]):
        try:
            return self._cache[block_type]
        except KeyError:
            return self._cache.setdefault(block_type, [])
    
    def _get_cached(self, block_type: type[GameBlock]):
        try:
            return self._get_cache(block_type).pop()
        except IndexError:
            return block_type()
    
    def _to_cache(self, block: GameBlock):
        self._get_cache(type(block)).append(block)

    def flush(self):
        for block in self._to_remove:
            self._pool.remove(block)
        self._pool.update(self._to_add)
        self._to_add.clear()
        self._to_remove.clear()

    def delete(self, block: GameBlock):
        if block in self._to_remove:
            return False
        self._to_remove.add(block)
        self._to_cache(block)
        return True

    def new(self, block_type: type[GameBlock]):
        block = self._get_cached(block_type)
        self._to_add.append(block)
        return block

    def clear(self):
        self._pool.clear()

class GameGrid(Matrix[GridSlot]):
    _OOBE = OutOfBoundsError()

    def __init__(
        self,
        renderer: ScreenRenderer,
        block_pool: BlockPool
    ):
        super().__init__(GameBlock._max_length)
        self._block_pool = block_pool
        self._ops = lt, ge
        self._layer = renderer.new_layer()
        self._view = self._get_view()

    @staticmethod
    def _new_cell(coord: Coord):
        return GridSlot(coord)

    def _get_slot(self, coord: Coord, block: type[GameBlock] | GameBlock):
        corners = [
            corner
            for i, (bounding, corner) in enumerate(
                zip(block._boundings, BOUNDING_CORNERS)
            )
            if self._ops[i//2](coord[i%2], bounding)
        ]
        if corners:
            wall_corners = WallCorners._get_cached()
            wall_corners.__init__(corners)
            self._OOBE.set_and_raise(wall_corners)
        return self[coord]
    
    def _erase(self, block: GameBlock):
        for coord in block._pos:
            try:
                self._get_slot(coord, block).remove(block)
            except MissingBlockError:
                pass

    def _apply_move(self, block: GameBlock, move: BlockMove):
        with BlockPos._enable_cache():
            pos = BlockPos._get_cached()
            pos.copy(block._pos)
            move._apply(pos)
            for src_coord, dest_slot in zip(
                block._pos,
                [self._get_slot(coord, block) for coord in pos]
            ):
                src_slot = self._get_slot(src_coord, block)
                src_slot.remove(block)
                dest_slot.add(block)
            block._pos.copy(pos)

    def _revert_move(self, block: GameBlock, move: BlockMove):
        with BlockPos._enable_cache():
            pos = BlockPos._get_cached()
            pos.copy(block._pos)
            move._revert(pos)
            for src_coord, dest_coord in zip(pos, block._pos):
                self._get_slot(dest_coord, block).remove(block)
                self._get_slot(src_coord, block).add(block)
            block._pos.copy(pos)

    def _draw(self):
        for y, row in enumerate(self):
            for x, slot in enumerate(row):
                self._layer[(x, y)] = slot and slot.front.color or None

    def _get_view(self):
        max_length = GameBlock._max_length
        return tuple(
            tuple(
                islice(
                    row,
                    max_length,
                    max_length + ScreenInfo.WIDTH
                )
            )
            for row in islice(
                self._matrix,
                max_length,
                max_length + ScreenInfo.HEIGHT
            )
        )
    
    def __iter__(self):
        return iter(self._view)

    def __repr__(self):
        return "\n".join(
            " ".join(str(slot._slot) for slot in row)
            for row in self._matrix
        )
    
N_BUTTONS = 10

class GPButtons():
    (
        ARROW_UP,
        ARROW_DOWN,
        ARROW_RIGHT,
        ARROW_LEFT,
        ARROW_UP_LEFT,
        ARROW_UP_RIGHT,
        ARROW_DOWN_LEFT,
        ARROW_DOWN_RIGHT,
        A,
        B
    ) = range(N_BUTTONS)

class GPPeriodicCallback():
    def __init__(self, repeat_every: int):
        self._repeat_every = repeat_every

    def _reset(self):
        self._counter = 0

    def _run(self):
        if self._counter % self._repeat_every == 0:
            self()
        self._counter += 1

    def __call__(self):
        raise NotImplementedError("You must overload this method")

class Gamepad():
    def __init__(
        self,
        on_press: dict[int, GPPeriodicCallback | Callable[[], Any]],
        on_release: dict[int, Callable[[], Any]]
    ):
        self._on_press = on_press
        self._on_release = on_release
        self._is_pressed = [False] * N_BUTTONS
        self._periodic_callbacks: list[GPPeriodicCallback] = []

    def _update_state(self, state: int):
        for i in range(N_BUTTONS - 1, -1, -1):
            is_pressed = bool(state % 2) if state > 0 else False
            was_pressed = self._is_pressed[i]
            self._is_pressed[i] = is_pressed
            try:
                if not was_pressed and is_pressed:
                    callback = self._on_press[i]
                    if isinstance(callback, GPPeriodicCallback):
                        callback._reset()
                        self._periodic_callbacks.append(callback)
                    else:
                        callback()
                elif not is_pressed and was_pressed:
                    try:
                        self._on_release[i]()
                    except KeyError:
                        pass
                    press_callback = self._on_press[i]
                    if isinstance(press_callback, GPPeriodicCallback):
                        self._periodic_callbacks.remove(press_callback)
            except KeyError:
                pass
            state //= 2

    def _run_periodic(self):
        for callback in self._periodic_callbacks:
            callback._run()

    def is_pressed(self, button: int):
        return self._is_pressed[button]

class GPBuilder():
    def __init__(self):
        self._instances: dict[str, Gamepad] = {}
        self._info: dict[str, dict[str]] = {}

    def _new_info_id(self):
        while True:
            id = f"#{randint(0, maxsize)}"
            if id not in self._info:
                return id

    def build(
        self,
        label: str,
        buttons: list[int], *,
        on_press: dict[int, Callable[[], Any]] | None=None,
        on_release: dict[int, Callable[[], Any]] | None=None
    ):
        id = self._new_info_id()
        self._info[id] = {
            "label": label,
            "buttons": buttons,
            "isConnected": False
        }
        return self._instances.setdefault(
            id,
            Gamepad(
                on_press or {},
                on_release or {}
            )
        )
    
    def _run_all_periodic(self):
        for instance in self._instances.values():
            instance._run_periodic()
    
GP_BUILDER = GPBuilder()

class ContinueOuterIteration(Exception): ...

class TransposeConflictError(ValuedException[GameBlock]): ...

type Collisions = dict[GameBlock, tuple[WallCorners | GameBlock, BlockMove]]
    
class GameEngine():
    _move_types: list[type[BlockMoves]] = [BlockShift, BlockRotate]
    _BCE = BlockConflictError()
    _RBE = RevertedBlockError()
    _TCE = TransposeConflictError()

    # Order here matters...
    # (Don't touch if you don't know what you're doing)
    def __init__(self, reporter: ErrorReporter):
        self._reporter = reporter
        self._loop = GameLoop()
        self._renderer = ScreenRenderer()
        self._animator = self._get_animator()
        self._block_pool = BlockPool()
        self._grid = GameGrid(self._renderer, self._block_pool)
        self._collisions: Collisions = {}
        self.on_init()

    def _get_animator(self):
        return Animator.new(
            self._loop,
            self._renderer,
            BlinkingXOnError,
            BlockBlinker
        )
    
    def _activate_error_animation(self):
        self._animator.get(BlinkingXOnError).activate()
    
    @classmethod
    def _get_implementation(cls, module: type):
        engine_cls = None
        block_classes = set[type[GameBlock]]()
        for name in dir(module):
            attr = getattr(module, name)
            if type(attr) is type:
                if (
                    issubclass(attr, GameBlock) and
                    attr is not GameBlock
                ):
                    block_classes.add(attr)
                elif (
                    issubclass(attr, cls) and
                    attr is not cls
                ):
                    engine_cls = attr
        if not engine_cls:
            raise RuntimeError(
                "Couldn't find any GameEngine "
                "implementation"
            )
        for block_class in list(block_classes):
            for base in block_class.__bases__:
                block_classes.discard(base)
        # Two separated for loops is intentional here
        for block_class in block_classes:
            block_class._process()
        for block_class in block_classes:
            block_class._post_process()
        return engine_cls

    def spawned_blocks(self):
        yield from self._block_pool

    def on_iteration(self): ...

    def on_init(self): ...

    @property
    def grid(self):
        return self._grid._view

    def _abort_swap(self, block: GameBlock, shift: BlockShift):
        for coord in block._pos:
            try:
                coord_ = shift._simulate(coord)
                block_ = self._grid[coord_].front
                if block_ is not block:
                    move_ = block_._get_move(BlockShift)
                    if move_._is_opposite(shift):
                        return block_, move_
            except (
                IndexError,
                MissingBlockError,
                MissingMoveError
            ):
                pass

    def _run_intention(self, move_type: type[BlockMove]):
        for block in self._block_pool:
            try:
                move = block._get_move(move_type)
            except MissingMoveError:
                continue
            if move_type is BlockShift:
                swapping = self._abort_swap(block, move)
                if swapping:
                    block_, move_ = swapping
                    self._collisions[block] = block_, move
                    self._collisions[block_] = block, move_
                    block_._abort_move(move_type)
                    block._abort_move(move_type)
                    continue
            try:
                self._grid._apply_move(block, move)
            except OutOfBoundsError as e:
                self._collisions[block] = e.value, move
                block._abort_move(move_type)

    def _run_resolution(self, move_type: type[BlockMove]):
        moving_blocks = [
            block
            for block in self._block_pool
            if block._wants_to_move(move_type)
        ]
        still_moving_blocks: list[GameBlock] = []
        shuffle(moving_blocks)
        while moving_blocks:
            block = moving_blocks.pop()
            try:
                for coord in block._pos:
                    slot = self._grid[coord]
                    if len(slot) > 1:
                        other = None
                        if len(slot) == 2:
                            other = next(
                                block_
                                for block_ in slot
                                if block_ is not block
                            )
                        move = block._get_move(move_type)
                        self._grid._revert_move(block, move)
                        block._abort_move(move_type)
                        moving_blocks.extend(still_moving_blocks)
                        still_moving_blocks.clear()
                        if other:
                            self._collisions[block] = other, move
                        raise self._RBE
                still_moving_blocks.append(block)
            except RevertedBlockError:
                pass
        for block in still_moving_blocks:
            block._abort_move(move_type)

    def _run_intention_resolution(self):
        move_types = self._move_types
        shuffle(move_types)
        for move_type in move_types:
            self._collisions.clear()
            self._run_intention(move_type)
            self._run_resolution(move_type)
            for block, (other, move) in self._collisions.items():
                block.on_collision(other, self, move)
        
    def is_nth_iteration(self, value: int):
        return self._loop.i % value == 0
    
    def spawn[C: GameBlock](
        self,
        block_cls: type[C],
        coord: Union[
            Coord,
            tuple[
                Union[int, SpawnDirective],
                Union[int, SpawnDirective]
            ]
        ],
        angle: int | SpawnDirective=BlockAngles.DEG_0,
        **callback_params
    ) -> C:
        if angle is SpawnDirectives.RANDOM:
            angle = randint(0, 3)
        elif not isinstance(angle, int):
            raise NotImplementedError(
                "Unknown angle's value "
                f"or directive: {angle}"
            )
        angle %= 4
        if isinstance(coord, tuple):
            c_values: list[int] = []
            for i, value in enumerate(coord):
                if isinstance(value, int):
                    c_value = value
                elif isinstance(value, SpawnDirective):
                    getters = SpawnDirectives._getter_map[value]
                    c_value = getters[angle * 2 + i](block_cls)
                else:
                    raise NotImplementedError(
                        "Unknown coordinate's value "
                        f"or directive: {value}"
                    )
                c_values.append(c_value + block_cls._boundings[i])
            coord = c_values
        with BlockPos._enable_cache():
            pos = BlockPos._get_cached()
            pos.__init__(coord, block_cls._offsets, angle)
            slots = [self._grid._get_slot(coord, block_cls) for coord in pos]
            clashing_blocks: set[GridSlot] = set(chain_from_iterable(slots))
            if clashing_blocks:
                self._BCE.set_and_raise(clashing_blocks)
            block = self._block_pool.new(block_cls)
            block._pos.copy(pos)
            block.on_spawn(**callback_params)
            for slot in slots:
                slot.add(block)
            return block

    def destroy_block(self, block: GameBlock, animate: bool=True):
        if self._block_pool.delete(block):
            self._grid._erase(block)
            if animate:
                blinker = self._animator.get(BlockBlinker)
                for coord in block._pos:
                    blinker.add_coordinate(coord)

    def destroy_cell(self, slot: GridSlot, animate: bool=True):
        for block in slot.flush():
            if animate:
                self._animator.get(BlockBlinker).add_coordinate(slot._coord)
            block._pos.remove(slot._coord)
            if not block._pos.has_cells():
                self._block_pool.delete(block)

    @contextmanager
    def _report_error(self):
        try:
            yield
        except Exception as e:
            if isinstance(e, KeyboardInterrupt):
                raise
            self._activate_error_animation()
            self._reporter.report_error(e)

    async def _run_loop(self):
        async for _ in self._loop:
            with self._report_error(), \
                self._animator as run_animations:
                self._renderer.render()
                run_animations()
                self._grid._draw()
                self._block_pool.flush()
                GP_BUILDER._run_all_periodic()
                with WallCorners._enable_cache():
                    self.on_iteration()
                    self._run_intention_resolution()

    @contextmanager
    def noclip_enabled(self):
        def move(
            block: GameBlock,
            moves: Iterable[BlockMove],
            filter_coords: Callable[[Coord], bool] | None=None
        ):
            pos = BlockPos._get_cached()
            pos.copy(block._pos)
            for move in moves:
                move._apply(pos)
            transposed[block] = (
                pos,
                [],
                filter_coords,
                {} if filter_coords else None
            )

        transposed: dict[
            GameBlock,
            tuple[
                BlockPos,
                list[tuple[GridSlot, GridSlot]],
                Callable[[Coord], bool] | None,
                dict[int, Coord]
            ]
        ] = {}
        with BlockPos._enable_cache():
            yield move
            dest_coords = set[Coord]()
            for block, (
                dest_pos,
                src_dest_slots,
                filter_coords,
                filtered_offsets
            ) in transposed.items():
                for i, (
                    src_coord,
                    dest_coord
                ) in enumerate(zip(block._pos, dest_pos)):
                    if filter_coords and not filter_coords(src_coord):
                        offset = dest_pos.to_offset(src_coord)
                        if offset in dest_pos.offs:
                            raise TransposeConflictError
                        filtered_offsets[i] = offset
                        continue
                    dest_slot = self._grid._get_slot(dest_coord, block)
                    if (
                        dest_coord in dest_coords
                        or dest_slot and
                        dest_slot.front not in transposed
                    ):
                        raise TransposeConflictError
                    dest_coords.add(dest_coord)
                    src_dest_slots.append((
                        self._grid[src_coord],
                        dest_slot
                    ))
            for block, (
                dest_pos,
                src_dest_slots,
                filter_coords,
                filtered_offsets
            ) in transposed.items():
                for src_slot, dest_slot in src_dest_slots:
                    src_slot.remove(block)
                    dest_slot.add(block)
                if filtered_offsets:
                    dest_pos.offs = tuple(
                        filtered_offsets.get(i) or off_
                        for i, off_ in enumerate(dest_pos.offs)
                    )
                block._pos.copy(dest_pos)

    async def __aenter__(self):
        self._heartbeat = create_task(self._run_loop())
        return self

    async def __aexit__(self, *_):
        self._loop.stop()
        await self._heartbeat
