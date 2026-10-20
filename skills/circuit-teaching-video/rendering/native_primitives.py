"""Native-density paint and reveal methods extracted from the production renderer."""
import io, math
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from matplotlib.mathtext import math_to_image
from matplotlib.font_manager import FontProperties
import logical_scene as layout


def image_bytes(value):
    seen = set()
    def visit(item):
        if id(item) in seen:
            return 0
        seen.add(id(item))
        if isinstance(item, Image.Image):
            return item.width * item.height * len(item.getbands())
        if isinstance(item, dict):
            return sum(visit(v) for v in item.values())
        if isinstance(item, (list, tuple)):
            return sum(visit(v) for v in item)
        return 0
    return visit(value)

class Lesson:

    @staticmethod
    def raster_scale(scale):
        # Oversample in bounded buckets; the final operation only downsamples.
        # This avoids expensive MathText rebuilds on every camera tween frame.
        return max(.25, math.ceil(scale * 4 - 1e-8) / 4)

    def native_event(self, event, scale):
        rs = self.raster_scale(scale)
        key = ("native", event["id"], rs, self.font_identity, event.get("formula"), event.get("size"), layout.BLACK, layout.GREEN)
        cached = self.cache.get(key)
        if cached is not None:
            return cached
        self.native_raster_calls += 1
        if event["kind"] == "formula":
            b = io.BytesIO()
            math_to_image("$" + event["formula"] + "$", b, dpi=150*rs, format="png", color=layout.BLACK,
                          prop=FontProperties(size=event["size"]*72/150))
            src = layout.math_style.color_feedback(Image.open(b).convert("RGBA"), event["formula"], event["size"], raster_scale=rs)
            native = {"im": src, "xy": (0, 0)}
            layout.pointer.prepare(native, formula=event["formula"], size=event["size"], raster_scale=rs,
                                   template=event["reveal_groups"])
        else:
            spec = event["im"].info["text_spec"]
            # Reuse the logical line breaks; resolution changes cannot reflow content.
            src = Image.new("RGBA", (math.ceil(event["im"].width*rs), math.ceil(event["im"].height*rs)))
            d = ImageDraw.Draw(src)
            font = ImageFont.truetype(str(layout.FONT), max(1, round(spec["size"]*rs)))
            for j, row in enumerate(spec["rows"]):
                d.text((0, round(j*(spec["size"]+12)*rs)), row, font=font, fill=spec["color"])
            native = {"im": src, "xy": (0, 0)}
            layout.pointer.prepare(native, size=spec["size"], raster_scale=rs)
        original = event["reveal_groups"]
        groups = native["reveal_groups"]
        if len(groups) != len(original):
            raise ValueError(f"Native reveal grouping changed: {event['id']} ({len(original)} -> {len(groups)})")
        for base, group in zip(original, groups):
            group["a"], group["b"] = base["a"], base["b"]
        native["raster_scale"] = rs
        self.native_records[(event["id"], rs)] = {"id": event["id"], "kind": event["kind"],
            "logical_size": list(event["im"].size), "native_raster_size": list(src.size),
            "raster_scale": rs, "font_dpi": 150*rs if event["kind"] == "formula" else None,
            "render_method": "MathText_at_native_DPI" if event["kind"] == "formula" else "FreeType_at_native_pixel_size",
            "preserved_reveal_groups": len(groups)}
        return self.cache.put(key, native, image_bytes(native))

    def paint_event(self, im, event, progress, tr, scale):
        if progress <= 0:
            return
        if event["kind"] == "asset":
            part, rs = self.asset_image(event, scale, progress)
        else:
            native = self.native_event(event, scale)
            rs = native["raster_scale"]
            if progress >= 1:
                part = native["im"]
            else:
                part = Image.new("RGBA", native["im"].size)
                layout.pointer.draw(part, native, progress)
        ratio = scale / rs
        size = (max(1, round(part.width*ratio)), max(1, round(part.height*ratio)))
        if part.size != size:
            part = part.resize(size, Image.Resampling.LANCZOS)
        ox, oy = event["origin"]
        x, y = event["xy"]
        im.paste(part, tuple(round(v) for v in tr((ox+x, oy+y))), part)

    def dot(self, im, point, opacity):
        s = self.config.ui_scale
        r, pad = 4*s, math.ceil(20*s)
        glow = Image.new("RGBA", (2*pad+1, 2*pad+1))
        d = ImageDraw.Draw(glow)
        d.ellipse((pad-r*1.6, pad-r*1.6, pad+r*1.6, pad+r*1.6), fill=(243,36,72,round(125*opacity)))
        glow = glow.filter(ImageFilter.GaussianBlur(5*s))
        d = ImageDraw.Draw(glow)
        d.ellipse((pad-r, pad-r, pad+r, pad+r), fill=(243,36,72,round(255*opacity)))
        d.ellipse((pad-1.5*s,pad-1.5*s,pad+1.5*s,pad+1.5*s), fill=(255,205,213,round(255*opacity)))
        im.paste(glow, (round(point[0]-pad), round(point[1]-pad)), glow)

    def asset_image(self, event, scale, progress):
        frames = event.get("progressive_frames", [])
        source = frames[min(len(frames)-1, int(progress*(len(frames)-1)))] if frames else event["asset_path"]
        rs = self.raster_scale(scale)
        size = tuple(max(1, round(x*rs)) for x in event["im"].size)
        key = ("asset", source, size, event["asset_sha256"])
        src = self.cache.get(key)
        if src is None:
            src = self.assets.rasterize(source, size)
            self.cache.put(key, src, image_bytes(src))
        if progress >= 1 or frames:
            return src, rs
        regions = event.get("asset_regions", [])
        if not regions:
            return src.crop((0, 0, round(src.width*progress), src.height)), rs
        part = Image.new("RGBA", src.size)
        for k, region in enumerate(regions):
            q = layout.clamp(progress*len(regions)-k)
            x0, y0, x1, y1 = [v*rs for v in region["box"]]
            box = (round(x0), round(y0), round(x0+(x1-x0)*q), round(y1))
            if q > 0:
                part.paste(src.crop(box), box[:2])
        return part, rs
