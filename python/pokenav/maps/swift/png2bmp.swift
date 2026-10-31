// png2bmp IN.png OUT.bmp : 24-bit BMP for levels.py (sips mangles palette PNGs)
import CoreGraphics; import ImageIO; import Foundation
let a=CommandLine.arguments
let s=CGImageSourceCreateWithURL(URL(fileURLWithPath:a[1]) as CFURL,nil)!; let img=CGImageSourceCreateImageAtIndex(s,0,nil)!
let W=img.width,H=img.height; var buf=[UInt8](repeating:0,count:W*H*4)
let ctx=CGContext(data:&buf,width:W,height:H,bitsPerComponent:8,bytesPerRow:W*4,space:CGColorSpaceCreateDeviceRGB(),bitmapInfo:CGImageAlphaInfo.noneSkipLast.rawValue)!
ctx.draw(img,in:CGRect(x:0,y:0,width:W,height:H))
let rs=(W*3+3) & ~3; var data=[UInt8](); data.reserveCapacity(rs*H)
for y in stride(from:H-1,through:0,by:-1){ for x in 0..<W { let i=(y*W+x)*4; data+=[buf[i+2],buf[i+1],buf[i]] }; data+=[UInt8](repeating:0,count:rs-W*3) }
func le32(_ v:Int)->[UInt8]{[UInt8(v&255),UInt8((v>>8)&255),UInt8((v>>16)&255),UInt8((v>>24)&255)]}
func le16(_ v:Int)->[UInt8]{[UInt8(v&255),UInt8((v>>8)&255)]}
var out:[UInt8]=[66,77]+le32(54+data.count)+le32(0)+le32(54)
out+=le32(40)+le32(W)+le32(H)+le16(1)+le16(24)+le32(0)+le32(data.count)+le32(2835)+le32(2835)+le32(0)+le32(0)
out+=data
FileManager.default.createFile(atPath:a[2],contents:Data(out))
