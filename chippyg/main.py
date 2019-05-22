#!/usr/bin/env python3

import copy
import os
import random
import sys
import time

import pygame


class CHIP8:
    clock_speed = 1000


def dbg(txt):
    print(txt, end='')


font_sprites = [ 
    [0xF0, 0x90, 0x90, 0x90, 0xF0], # 0
    [0x20, 0x60, 0x20, 0x20, 0x70], # 1
    [0xF0, 0x10, 0xF0, 0x80, 0xF0], # 2
    [0xF0, 0x10, 0xF0, 0x10, 0xF0], # 3
    [0x90, 0x90, 0xF0, 0x10, 0x10], # 4
    [0xF0, 0x80, 0xF0, 0x10, 0xF0], # 5
    [0xF0, 0x80, 0xF0, 0x90, 0xF0], # 6
    [0xF0, 0x10, 0x20, 0x40, 0x40], # 7
    [0xF0, 0x90, 0xF0, 0x90, 0xF0], # 8
    [0xF0, 0x90, 0xF0, 0x10, 0xF0], # 9
    [0xF0, 0x90, 0xF0, 0x90, 0x90], # A
    [0xE0, 0x90, 0xE0, 0x90, 0xE0], # B
    [0xF0, 0x80, 0x80, 0x80, 0xF0], # C
    [0xE0, 0x90, 0x90, 0x90, 0xE0], # D
    [0xF0, 0x80, 0xF0, 0x80, 0xF0], # E
    [0xF0, 0x80, 0xF0, 0x80, 0x80]  # F
]
font_sprite_start = 0x00
FONT_MAP = {i:font_sprite_start+(i*5) for i in range(0x10)}
scancodes = [
    82, 79, 80, 81, 75, 76, 77, 71, 72, 73,
    59, 60, 61, 62, 63, 64
]
KEY_MAP = {sc:i for i, sc in enumerate(scancodes)}



class EmuError(Exception):
    pass


class OpDecode:
        
    @staticmethod
    def _0000(chip):
        op = chip.opcode & 0x00FF
        if op == 0x00E0:
            chip.clear_disp()
        elif op == 0x00EE:
            chip.stackpos -= 1
            chip.pc = chip.stack[chip.stackpos]
        else:
            raise EmuError(chip.opcode)
        chip.pc += 2

    @staticmethod
    def _1000(chip):
        addr = 0x0FFF & chip.opcode
        chip.pc = addr

    @staticmethod
    def _2000(chip):
        chip.stack[chip.stackpos] = chip.pc
        chip.stackpos += 1
        addr = chip.opcode & 0x0FFF
        chip.pc = addr

    @staticmethod
    def _3000(chip):
        vx = chip.cpureg[(chip.opcode & 0x0F00) >> 8]
        if vx == chip.opcode & 0x00FF:
            chip.pc += 2
        chip.pc += 2

    @staticmethod
    def _4000(chip):
        vx = chip.cpureg[(chip.opcode & 0x0F00) >> 8]
        if vx != chip.opcode & 0x00FF:
            chip.pc += 2
        chip.pc += 2

    @staticmethod
    def _5000(chip):
        if chip.opcode & 0x000F != 0x0000:
            raise EmuError(chip.opcode)
        vx = chip.cpureg[(chip.opcode & 0x0F00) >> 8]
        vy = chip.cpureg[(chip.opcode & 0x00F0) >> 4]
        if vx != vy:
            chip.pc += 2
        chip.pc += 2

    @staticmethod
    def _6000(chip):
        addrx = (chip.opcode & 0x0F00) >> 8
        chip.cpureg[addrx] = chip.opcode & 0x00FF
        chip.pc += 2

    @staticmethod
    def _7000(chip):
        addrx = (chip.opcode & 0x0F00) >> 8
        vx = chip.cpureg[addrx]
        chip.cpureg[addrx] = (vx + (chip.opcode & 0x00FF)) % 256
        chip.pc += 2

    @staticmethod
    def _8000(chip):
        lb = chip.opcode & 0x000F
        addrx = (chip.opcode & 0x0F00) >> 8
        addry = (chip.opcode & 0x00F0) >> 4
        valx = chip.cpureg[addrx]
        valy = chip.cpureg[addry]
        if lb == 0x0000:
            chip.cpureg[addrx] = chip.cpureg[addry]
        elif lb == 0x0001:
            chip.cpureg[addrx] = valx | valy
            chip.cpureg[addrx] = chip.cpureg[addry]
        elif lb == 0x0002:
            chip.cpureg[addrx] = valx & valy
        elif lb == 0x0003:
            chip.cpureg[addrx] = valx ^ valy
        elif lb == 0x0004:
            if valx + valy > 255:
                chip.cpureg[0xF] = 1
            else:
                chip.cpureg[0xF] = 0
            chip.cpureg[addrx] = (valx + valy) % 256
        elif lb == 0x0005:
            if valx - valy < 255:
                chip.cpureg[0xF] = 0
            else:
                chip.cpureg[0xF] = 1
            chip.cpureg[addrx] = abs(valy - valx) % 256
        elif lb == 0x0006:
            chip.cpureg[0xF] = valx & 0x0001
            chip.cpureg[addrx] >>= 1
        elif lb == 0x0007:
            if valy - valx < 255:
                chip.cpureg[0xF] = 0
            else:
                chip.cpureg[0xF] = 1
            chip.cpureg[addrx] = abs(valx - valy) % 256
        elif lb == 0x000E:
            chip.cpureg[0xF] = valx & 0x80
            chip.cpureg[addrx] <<= 1
        else:
            raise EmuError(chip.opcode)
        chip.pc += 2

    @staticmethod
    def _9000(chip):
        if chip.opcode & 0x000F != 0x0000:
            raise EmuError(chip.opcode)
        addrx = (chip.opcode & 0x0F00) >> 8
        addry = (chip.opcode & 0x00F0) >> 4
        if chip.cpureg[addrx] != chip.cpureg[addry]:
            chip.pc += 2
        chip.pc += 2

    @staticmethod
    def _A000(chip):
        chip.ireg = chip.opcode & 0x0FFF
        chip.pc += 2

    @staticmethod
    def _B000(chip):
        chip.pc = chip.cpureg[0x0] + chip.opcode & 0x0FFF

    @staticmethod
    def _C000(chip):
        addrx = (chip.opcode & 0x0F00) >> 8
        val = chip.opcode & 0x00FF
        chip.cpureg[addrx] = random.randint(0, 255) & val
        chip.pc += 2

    @staticmethod
    def _D000(chip):
        addrx = (chip.opcode & 0x0F00) >> 8
        addry = (chip.opcode & 0x00F0) >> 4
        valx = chip.cpureg[addrx]
        valy = chip.cpureg[addry]
        n = chip.opcode & 0x000F
        chip.draw(valx, valy, n)
        chip.pc += 2

    @staticmethod
    def _E000(chip):
        addrx = (chip.opcode & 0x0F00) >> 8
        valx = chip.cpureg[addrx]
        op = chip.opcode & 0x00FF
        if op == 0x009E:
            if chip.keys[valx]:
                chip.pc += 2
        elif op == 0x00A1:
            if not chip.keys[valx]:
                chip.pc += 2
        else:
            raise EmuError(chip.opcode)
        chip.pc += 2

    @staticmethod
    def _F000(chip):
        addrx = (chip.opcode & 0x0F00) >> 8
        valx = chip.cpureg[addrx]
        op = chip.opcode & 0x00FF
        if op == 0x0007:
            chip.cpureg[addrx] = chip.delay_timer
        elif op == 0x000A:
            raise NotImplementedError(chip.opcode)
        elif op == 0x0015:
            chip.delay_timer = valx
        elif op == 0x0018:
            chip.sound_timer = valx
        elif op == 0x001E:
            if chip.ireg + chip.cpureg[addrx] > 0xFFF:
                chip.cpureg[0xF] = 1
            else:
                chip.cpureg[0xF] = 1
            chip.ireg = (chip.ireg + chip.cpureg[addrx]) & 0xFFF
        elif op == 0x0029:
            chip.ireg = FONT_MAP[valx]
        elif op == 0x0033:
            dec = '{:03}'.format(valx)[-3:]
            for i, c in enumerate(dec):
                chip.mem[chip.ireg+i] = int(c)
        elif op == 0x0055:
            for i in range(addrx+1):
                chip.mem[chip.ireg + i] = chip.cpureg[i]
        elif op == 0x0065:
            for i in range(addrx+1):
                chip.cpureg[i] = chip.mem[chip.ireg + i]
        else:
            raise EmuError(chip.opcode)
        chip.pc += 2


class Chip8:

    
    def __init__(self):
        self.opcode = 0
        self.cpureg = [0] * 16
        self.ireg = 0
        self.pc = 0x200
        self.delay_timer = 0
        self.sound_timer = 0
        self.stack = [0] * 16
        self.stackpos = 0
        self.keys = [0]*16

        self.init_memory()
        self.clear_disp()

        self.draw_flag = True

        self.now = self.last = self.last_counter = time.perf_counter()


    def print_hist(self):
        out = []
        if self.prev.cpureg != self.cpureg:
            for i in range(len(self.cpureg)):
                if self.prev.cpureg[i] != self.cpureg[i]:
                    out.append('V{:X}:{:02X}->{:02X}'.format(
                        i, self.prev.cpureg[i], self.cpureg[i]))
        if self.prev.gfx != self.gfx:
            for y in range(32):
                for x in range(64):
                    coord = x + y*64
                    if self.prev.gfx[coord] != self.gfx[coord]:
                        out.append('({},{}): {}->{}'.format(
                            x, y, self.prev.gfx[coord], self.gfx[coord]))
        if self.prev.mem != self.mem:
            for i in range(len(self.mem)):
                if self.prev.mem[i] != self.mem[i]:
                    out.append('${:04X}: {:04X}->{:04X}'.format(
                        i, self.prev.mem[i], self.mem[i]))
        if self.prev.ireg != self.ireg:
            out.append('ireg: {:04X}'.format(self.ireg))
        if self.prev.stack != self.stack:
            out.append('stack: {}'.format(self.stack))
        if self.prev.stackpos != self.stackpos:
            out.append('stackpos: {}'.format(self.stackpos))
        if self.prev.delay_timer != self.delay_timer:
            out.append('delay timer: {}'.format(self.delay_timer))
        for o in out:
            print('    ' + o)
        self.prev = copy.deepcopy(self)


    def clear_disp(self):
        self.gfx = [0] * (64*32)

    def init_memory(self):
        self.mem = [0] * 4096
        i = 0
        for letter in font_sprites:
            for bitmask in letter:
                self.mem[font_sprite_start+i] = bitmask
                i += 1

    def draw(self, start_x, start_y, sprite_height):
        if not self.draw_flag:
            return
        if start_x > 63:
            start_x = start_x % 64
        if start_y > 31:
            start_y = start_y % 32
        flipped = False
        for j in range(sprite_height):
            y = start_y+j
            if y > 31:
                continue
            new_sprite = self.mem[self.ireg + j]
            new_pixels = (int(c) for c in '{:08b}'.format(new_sprite))
            for i, pixel in enumerate(new_pixels):
                x = start_x+i
                if x > 63:
                    continue
                coord = x + y*64
                old_pixel = self.gfx[coord]
                if old_pixel & pixel:
                    print('collision ({},{})'.format(x, y))
                    flipped = True
                self.gfx[coord] = old_pixel ^ pixel
        if flipped:
            self.cpureg[0xF] = 1
        else:
            self.cpureg[0xF] = 0


    def get_opcode(self):
        op_1 = self.mem[self.pc]
        op_2 = self.mem[self.pc + 1]
        self.opcode = op_1 << 8 | op_2
        addr = (self.opcode & 0x0F00) >> 8
        op = '{:04X} V{:X}: {}'.format(self.opcode, addr, self.cpureg[addr])

    def exec_opcode(self):
        op = '_{:0>4X}'.format(0xF000 & self.opcode)
        func = getattr(OpDecode, op)
        func(self)

    def decr_registers(self):
        if self.delay_timer == 0 or (self.now-self.last_counter) < (1/60):
            return
        amount_to_dec = int((self.now-self.last_counter) / (1/60))
        self.delay_timer = max(self.delay_timer - amount_to_dec, 0)
        self.last_counter = self.now

    def emulate_cycle(self):
        self.decr_registers()
        self.now = time.perf_counter()
        while self.now - self.last < 1/CHIP8.clock_speed:
            self.emulate_cycle()
        self.get_opcode()
        #print('{:04X} {:04X}'.format(self.pc, self.opcode))
        self.exec_opcode()
        #self.print_hist()
        self.last = self.now

    def load(self, game):
        with open(game, 'rb') as f:
            for i, b in enumerate(f.read()):
                self.mem[0x200 + i] = b
        self.prev = copy.deepcopy(self)

    def store_keys(self):
        pass


def init_graphics():
    pygame.init()
    return pygame.display.set_mode((64,32))


def init_input():
    pass


def main(game_filename):
    screen = init_graphics()
    pixels = pygame.PixelArray(screen)
    init_input()

    chip = Chip8()
    chip.load(game_filename)

    val = 0
    while True:
        chip.emulate_cycle()
        chip.store_keys()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.scancode in KEY_MAP:
                    chip.keys[KEY_MAP[event.scancode]] = 1
            elif event.type == pygame.KEYUP:
                if event.scancode in KEY_MAP:
                    chip.keys[KEY_MAP[event.scancode]] = 0
        for x in range(64):
            for y in range(32):
                if chip.gfx[x + y*64] == 1:
                    value = (255, 255, 255)
                else:
                    value = (0, 0, 0)
                pixels[x][y] = value
        pygame.display.flip()
        if val >= 255:
            val = 0
        else:
            val += 1


if __name__ == '__main__':
    main(sys.argv[1])
