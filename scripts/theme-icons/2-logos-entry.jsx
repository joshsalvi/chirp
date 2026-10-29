import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { THEMED_LOGOS } from '../src/components/ThemedChirpLogos'
import SongbirdMark from '../src/components/SongbirdMark'
const SIZE = Number(process.env.LOGO_SIZE || 64)
const out = {}
for (const [id, L] of Object.entries(THEMED_LOGOS)) out[id] = renderToStaticMarkup(<L size={SIZE} animate={false}/>)
out.__default = renderToStaticMarkup(<SongbirdMark size={SIZE} animate={false} ink="INK" catchlight="BG" accent={['B0','B1','B2']}/>)
process.stdout.write(JSON.stringify(out))
