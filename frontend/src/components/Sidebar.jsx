import { NavLink, useNavigate } from "react-router-dom";
import { ForkKnife } from "phosphor-react";
import {
  FiSun,
  FiMoon,
  FiX,
  FiUser,
  FiLogOut
} from "react-icons/fi";

import { useTheme } from "../context/ThemeContext";
import { useState, useRef, useEffect } from "react";

export default function Sidebar({ closeSidebar }) {

  const { theme, toggleTheme } = useTheme();
  const [showProfileMenu, setShowProfileMenu] = useState(false);
  const profileRef = useRef(null);
  const navigate = useNavigate();

  const role = localStorage.getItem("role");
  const userId = localStorage.getItem("user_id");

  /* ================= SVG ICONS ================= */

  const IconWrapper = ({ src, alt }) => (
    <img
      src={src}
      alt={alt}
      className="w-5 h-5 object-contain dark:invert dark:brightness-200"
    />
    
  );

  const InventoryIcon = () => (
  <IconWrapper alt="inventory"src="data:image/png;base64,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"/>);

  const DishIcon = () => <IconWrapper alt="dish" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFoAAABaCAYAAAA4qEECAAAACXBIWXMAAAsTAAALEwEAmpwYAAAFLUlEQVR4nO2d34uVRRjHP7Rbu6UVQeHuMaiwuukmUulCIzHTDCK7qMAsKjMIAzWx3IvIgsi86MeG/RlaSRTrRd0VcWJbLerG6MLS2jymXrhL204MPAeWw5497zvzzLxzzs4HHlgO58w7z3fnzI9nnpkDmUwmk8lkMplMJpMpTB+wGtgOHAI+AU4Ap4AGMC3WkNdOyHvelc+skjIy83AzsBs4BlwAjKf9A3wG7AKWs8i5GngaOA78pyBuO5sBxoBtwCCLiKXS0n4PKG47+ws4AFxPD3MlsA84V4HArWbrsFfq1FPcB5xMQOBW+wXYQA9g+8TDwGwCorYzW7dRYIAu5Vbg2wSENAXte+B2uowNStM0E9nstHA9XcJjwOUERDOOZhdDT5I4LwaeE5tIZn3YQaJskcVB1SIZRbGfIDFsvzaVgDgmQDeykUS4o0sHPlNigFxRtcgDMi0yPW71qufZhx0q/VakWcnfwIfy1a8BNwA3AeuA94CLJcuzi5pKuN9hxVeXzz4UUOzL8s+8pkP9lwFflSjX+rqWyNhgzI8OIrw0p4wQYv8hgf8yfnxdony7ydBPRPY5CnFnSzmbFcU+Ddzi4Itt2ZdKPGcPkbjWMdR5tk15GmLbqeXdHj59UOJZkxJTD86rjmLUFyjTV+zXPX16oOTzbCw7+PbTWUcxPu9QtqvYGi3sRoexIOi22DMerW6sQPkbHcR+X6k7LOvPVgJy3EPoesFnlG3ZGkvk5Q7+fEnAlACfyFwDuCKA2EMKvj3s4I8NoA0TgN0eIhuxu0o8r6jYGn3lx47+vEwAjikIvafkM4uIbQcyH5bKt83Fn6Mo0y9RLF+hf3J4diexbezCh3c8/Glop5+tVhDZiG1SFNsuVNZ4+HWvQhx9JYpsVxT6Z+AqR7HnijIlr7lil+tnFPx5DkUOKQptgLcd69EU21fklYopaQdR5FNloWcl6dCFzR4i24XJm7JFpeWL6oA4oSy0UWiV7Vgje5hDEpOuSUj2I9kM0PZjXLPyvwWooJGW9YhiPTdVkFPyq2L9g2aATiuJXYXIzaCWGpp9mgkgdlUiN7vArhHaeIhdpcjqQsdKHp8uKXbVIqt3HaEGQ+Mhdgoiqw+GIaZ3xmPa17pKbLV/I9Z3POUFi/FozZ1a8huRW/uRlJfgJqDIRd+rZTb6l2RQyUQQOabYz6YaJjUB+uQDHp/1tXs0he5TCvybQAOfbxnJBP6Rs9WpdRcmQFmVDYRNdiXWkk2EMjvZTgJQUzqjMh2w9cVs2TNKqQ7zMpZgSzYVtewvCMg2z8q9FkGAomLv93xG0JSwQc+9tqGIg1WnbmSZR9lnJOEzySR0s0AKVaiFxUJi1zzKfYWEE9ENMFLBgqJdNzLiERZdQiT2erSwEWlNNfk7xkHQKemTh8X2e2xm2GluNGyK2A8RBDKJ2ckqbq1Zm/iFJ0bZZuXIXyWMJiCAiWT2QFFlDEgmv+lx+84xX1CVFYEieyYROw/cRiKsS2Sj1CibnZk8SGI82oMXozxOouzokat+ZoAXSJwtXd6NTKV4xU871nfpAHle4UxMdOzRhW8SEM8UtHoKV/r4zLNHE19BzspipPJ5stZyfSIBUVttwvNUV5L0y4HOyQQEnpQoXNTbZGKzRJw8XYHAf0qyzXUsIgaBp+SWgJALnRnZSN262K6en49hOcB+1ONc9lxrSFk7Q6YEdDt9ks/2vByWPCI5yKdkC6358yDn5LVxec9BOcVqP5t/HiSTyWQymUwmk8lkKMj/cZH+tPT39xAAAAAASUVORK5CYII=" />
  const OrderIcon = () => <IconWrapper alt="order" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFoAAABaCAYAAAA4qEECAAAACXBIWXMAAAsTAAALEwEAmpwYAAADZklEQVR4nO2cXYtNURjHf8XMEHJphgsG1y4UhWj4CkK4cOWlXMiYcqV8AS/DBebCB6CUyCRvuRYN5eVW1ITxNhSDsbSmtYvT7OPsM8+z91rnPL/613Tas/ez/u291rOf9ZwDhmEYhmEYhmEYxozYDAwBz4GvQf7vC0DfzE5teFYAdwD3H90Ceqf+wyjMemCsAZMzvQPWFb9Me7MMeFvA5Exj4SkwGuR2EyZnutvoRdqdLTMwOZMtkA0wlGPeN+Aw0A30AP3hs+mOPd/IhdqdFznmeZNrOZJz7LMK4k6OLznm+Tu5lu6cY8criDs5PhUwenHOsR8riDs5RnLM83NyLQM5xz6qIO7kOFtnMewPC2FPmJ+/5xw7WPUgUmCtQHq3pupBxMoiYC9wGXgvYLQ/x6VwTn/utqYD2A5cB34KmJsnf+5rwLZwzbZhPnAIeKlobp5GgePAQlqYWcCBUGVzFcsXrPaHmFqKDcCTCAyu1UirlFY7wqP6KwJT8zQZ0sEuEqW3zsuHi1APgaUkRp/iXDwcpHHuN8BGEmEH8EPR5DlBWmZPAFuJnF2KOfHNYHBGZ8iPNa7l15Q9RMrOsLBo3sm1aN7Zk+ElJyo21SnwuIKSQmoa8VtrUbAS+CB4J0khFY+vmyynYrpCWiT5yEohGdODsCZEVztuNaMdcJKK8Pnm7zYyejJ0T5WKf4yeKgxmWDBGjWzkcdml1oESU7hm0Ur9fIm3tHpyM31xrsDLiBQaLzW+tLCAEjiWiMmaZh9Fmc5QeJE2em5iRo9qp3u7hQN2ymZr1kP8fqca95WCdgkthpnuocQSpbzZ1ZgthabJWV7tW9LEOagcuAuSooxY/WazOH4eNaP5RzcQZnaddtp2NnpcumVhdUmBO8GYy4p3lWDMU3ORGc202icYM6dLDNwVyLM18+RGdULS6KsVD8ZNY3YMJntdkTQ6lnau4RLaDYrKNwmJ8TqCAbm/zI7FZK9XZXyBx8TUxrQYWp1HrgXkWxLEqHowLnKZ0ZjRtJLMaMxoWklmNIkZbRiGYRiGoce88GtbnyNIn1wCFbzBZhuALkYwAJeYzhQ12TdbW2mUwvJPf+E+jokIAneJyW+QFMamDgprsNnF8JxtY9HodxFPpfxTFIZhGIZhGIZhGIZhGIZhGOjyB2pWg4J113iRAAAAAElFTkSuQmCC" />
  const WastageIcon = () => <IconWrapper alt="wastage" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFoAAABaCAYAAAA4qEECAAAACXBIWXMAAAsTAAALEwEAmpwYAAACuklEQVR4nO3cz2oTURTH8a8KjX+6tZuiC7H6ABYfwC50o0LfoC4EwZb6BHUtEmtFcBOfINIHqFut1kXdRleiQtyoqNi6kCMXRgghkxC8dX5zej7wg1KScOfXMLk5TQZCCCGEEEIIIYQQwl46DDSBLmAC+QjcBSZwZk2g3EFJf3w3DgBfBEodlLSuyhwFHgJfBYqwPc7vKot+JFCA/cdU4iDwU+Dgzfszer8V/ZkK7adTR7PKoo8AD4R3CpYhH4A7HvfRIYQQQgjD7QpsxSxzdhD0SaAYy5w0E5fzRqAYy5wOgl4JFGOZs4WgpwLFWOZsIOiJQDGWOW0EPRYoxjKnhaB7AsXYfviH7G2BYixzVhC0LFCMZU46JjkLAsVY5qRjkjMvUIxlTjomOXMCxVjmXEDQrEAxljnnEDQjUIxlzmkETQkUY5lzHEENgWIsc9IxSfI0/N9BmKfhfxdhnob/HYR5Gv5vIczT8H8DYZ6G/22EeRr+txDWFCjIPA/9/1oRKMg8D/09Dv+XEeZp+L+AME/D/3mEeRr+zyHM0/B/FmGehv8zCPM0/J9CWB2H/++KS1dcBM4Cx4qkbwZL263RFzWvA4eoKZUrx9iQrAOT1FxHoEgbktU6nBbqPvxf91IyxcDcBPPew+miV1ugVBuQayN2S0vAC+BHkfTzovJHDloCpdqALVzZ7mIaeD3kvtvFbeQoDv/XStbaGFFyb9lyz2zFT/5fKlnr0hiPcRMxtwSKtb6cKVnryzEeYxMxisP/yZK1fh/jMdJtpVwRKNb6kq799K9Ff0PMKYFirS8nPZ46kmcC5VpPLpesc7HOL4bJebEp3mrJOhvF1m3U/beVL8d2tTivmUC6Q4qaHlG27BuWXieA+8Bb4FfFZd8Yss6J4tSwWbxApjwvfif7TA4hhBBCCCGEEEKgIn8AF0ecAZxt630AAAAASUVORK5CYII=" />
  const RemainingIcon = () => <IconWrapper alt="remaining" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFoAAABaCAYAAAA4qEECAAAACXBIWXMAAAsTAAALEwEAmpwYAAAEj0lEQVR4nO2cz29VRRTHP2J8j19GW0ojmigW3MrSxGAL/AeEBRYNjRjUVRMTVrDwBwmVjYGWShMFUkvQhRtdAAuNyBohRaLoRk1IYAEiChSbtmMmmZfQ5M3c275758zcN5/kbF7eu+fMN/fNPWfmzIVEIpFIJBKJmFGRWzRIC6WS0ERh0SAtlEpCE4VFg7RQKglNFBYN0kKpJDRRWDRIC6WS0ERh0SAtlEpCk8tmgYvAIeAtYBPQA3QANWMd5rNN5juHgUvmt0lo3OJ+C+wEOlvwvQoYAL5rQfRoWMig7gNHgLUlxKGvOQpMtbPQc8Ax4CkP8awBThiflRF6fY6B/Ay8LBDbRuBqjvjWETidOQbyObBSMMZlwKcZMf4CPEmg6EzgfMbDbpBweDfjYXkGeJQAOegIehroJzx2mNhscesxBcVmx90xW7DISyhebFvsM8BLBMJy4E/HXTFY4Nyq08C/jY2Yz4qaRmzxXzHTojgfOIIcL9DPoSbX/7jA6590jON9hHnOFBy2FG5Fgb5uNPFxvcDrr3RkTHeB1Qgy5ihGegv2pTwUFxsdRc0QQnQ77ubPSvCnPAiNme6a+fkX6EKADy0B3S+prFaehH4aeGDxtQ/PPAL8bglGZwNELLTmqKNi9EqvI2cuYxXOt9DPO3LrDXjkE0sQej2ZCgit+d7xUCy6aLLymyUIvWhfFaF3WfzdAW6XUDQ1fVjYpo1WdkZCE3p1zvXrIoumebxqcaj3+KiQ0JrJHEIXWTTlSut0iVw1oYdzCF1aDF9anO2mekK/Iyn0jxZnfVRP6M2SQv9hcVZW/iwpdI+k0LcsznQ/RVnUhYTukhT6P4uzshbHa8A3QkLX20XoWobI16iw0Dc9TR114HTGAIeqPHX4eBjWc4h82nyvsg/DCyWnd/VARBZP78osWGoZc7K2s8BS/CBasNhKcN2f3ApLcojs605uMCIp9HaLM90E3grbAhNZczmHyH9JLJO2knnsD0zk7pzLpHrhqTR+tTjVnfaLpT8gkTVvWuL5B7hnej2Olv28GLUEoY8zLJbHzO8fvt7XQiJnbWV54xXH9LG2RbF3mDazrT735prkz7bN2RdDaTfQjYixMxZKu4GruXHKnBmJlWccDTR7Q2sJO068TDh2v8vcfF5Uf8echx2XMnA1OR5AkGcdd/VV4UNBC+VxR7+KeNsupknblszrv2EsfOEYx3sEcrTCtnSqzLGF0NnjiP+nUI5WNPLqGcd8PUC4uA4LzQodPHUy5LgrpoHXCI/XM46/fUSA6KruB0fQc4FNI3syFo2CPdCJyTNtC07K2FfAE8LZxamYjyg3eCFjEMqkfnpe902fI4WL6tB9g6yBKPO3HTfr2z7K6omqvUaCnINRxh6YClMfZyhjFW7MsXbRVkKrh1IpvQb8RotVWLdZtD+XXvVDrmll0mwTvW22/deZh23j5VWrzEtYtpjd6mGzx5d3ekhCI2/RIC2USkIThUWDtFAqCU0UFg3SQqkkNFFYNEgLpZLQRGHRIC2USkIThUWDtFCqXYROJBKJRCKRYB7/A9OrwbWUNxbeAAAAAElFTkSuQmCC" />
  const ReportsIcon = () => <IconWrapper alt="reports" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAFoAAABaCAYAAAA4qEECAAAACXBIWXMAAAsTAAALEwEAmpwYAAADb0lEQVR4nO2dTW+NQRTHfxG97KtFNdGISCohWHgLCxsrG74HfaFpYsGmwcqKj0AsvH4BdCHSxoKwRyxI1EIoVY0jk0xEpPdpr5nnOTPnzj/5b27vnZnzu8+dO88507lQVFRUVFRUVJST1gMjwAzwFRBF/wCeAPsxpkHghTJcWcbfgeMYupJThCzWYI8kAFO6AfZMAiClG2B/SQCi/OV5q7AlMR9d4c1fAE6QoSQxYxV2iqBNwk4VtDnYKYM2BTt10GZg5wDaBOxcQGcPOyfQWcPODXS2sHMEnSXsXEFnBztn0FnBzh10NrAtgHY6tooUq2oNUhLzQI2wXcFXTZKYJwPjqYLtqutq0gYry8CYrPHKVpN0mdWkHbgU0DatJu3ApYC2aTVpBy4FtE2rSTtwKaBtWk3agUsBbdNq0g5cCmibVpN24FJA27SatAOXAtqm1aQduBTQNr22gKYRvweuANsLaBrxL+A2sLWAphF/Ay4CrQKaRuw212wqoGnEb4E9BTTLegl4BIwCB4B+oMe73z825p+ztIr2PgHDBTR/7A5vmQJ6O4i117+man+e85vAnVJmQN8ANgfE7CDeXKGPZ/5TEU2SkZcibIL896ySqunkfMS+soJ8kvg6VQHb7aneEasjycRnqU8TFf3ejdWJZDIn161bFZ+kbTE6kAzu3AapXwMVq5GrMTqQxD1Fc7pUsbZeE9q4JOyfHa6TQ9VX8cW4L7RxSdgPaV7TbcYyHtqwJOxRmtd4XasPSdgHaF6H24zFnQ8YJEnYfTSvjW3G8jq0YUnYLZrXujZjcUu/IFkFLZG9YBl0X0JxfbQM+mBCcb2yDHosobjuWAb9OKG4Lli/Bd+QSFxHLIOWgKRSzDHMxShridE0qUT0tVDIOYAWX0jVisttHdtt8eh5aeNzSqDv0WU/prDkC6lNgnan4eyMBfpMAhClA9gTDYK+TOQkyvMEIEoHdoXULTWDnq0jqTWYIex5X+Nrlw8J3aw+RE1yV/Zp4GlGX5Dip5Npv+/jkM8ntwLa+wzspcu0C3jX4Jv2IUYRNlcN+fmybsizdU4XuajlVwCLNQBe9G1rVHOS1TDwwN+thQJ2bdyPuU62Ondf98meTgHP+dxFlNvqblGPPzva/VeVS8y/9Nu33B2ds4PqHnN/c89xqc7/zsL9BnsDqNKPen6eAAAAAElFTkSuQmCC" />

  /* ================= CLOSE PROFILE ================= */

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setShowProfileMenu(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  /* ================= LOGOUT ================= */

  const handleLogout = () => {
    localStorage.clear();
    navigate("/login");
  };

  /* ================= LINK STYLES ================= */

  const quickDishClass = ({ isActive }) =>
    `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200
    ${isActive
      ? "bg-orange-500 text-white shadow-md scale-[1.02]"
      : "bg-orange-500 text-white hover:bg-orange-600"
    }`;

  const normalLinkClass = ({ isActive }) =>
    `flex items-center gap-3 px-4 py-3 rounded-xl text-sm font-medium transition-all duration-200
    ${isActive
      ? "bg-orange-100 text-orange-700 dark:bg-orange-500/20 dark:text-orange-300 scale-[1.02]"
      : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800"
    }`;

  return (
    <aside className="w-64 max-md:w-60 bg-white dark:bg-[#0f172a] border-r border-gray-200 dark:border-gray-800 min-h-screen flex flex-col transition-all duration-300">

      {/* LOGO */}
      <div className="flex items-center justify-between px-6 py-5 border-b border-gray-200 dark:border-gray-800">
        <div className="flex justify-center w-full">
          <img src="/logo.svg" alt="logo" className="h-12 w-auto" />
        </div>

        {closeSidebar && (
          <button onClick={closeSidebar} className="md:hidden p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800">
            <FiX />
          </button>
        )}
      </div>

      {/* NAV */}
      <nav className="px-4 py-6 flex-1 overflow-y-auto space-y-2">
{/* 
        <NavLink to="/quick-dish" className={quickDishClass}>
          <ForkKnife size={20} />
          Quick Dish
        </NavLink> */}

        <NavLink to="/inventory" className={normalLinkClass}>
          <InventoryIcon />
          Inventory Management
        </NavLink>

        <NavLink to="/dish-preparation" className={normalLinkClass}>
          <DishIcon />
          Dish Management
        </NavLink>

        <NavLink to="/orders" className={normalLinkClass}>
          <OrderIcon />
          Order Management
        </NavLink>

        <NavLink to="/wastage" className={normalLinkClass}>
          <WastageIcon />
          Wastage
        </NavLink>

        <NavLink to="/remaining-inventory" className={normalLinkClass}>
          <RemainingIcon />
          Remaining Inventory
        </NavLink>

        <NavLink to="/reports-analysis" className={normalLinkClass}>
          <ReportsIcon />
          Reports and Analysis
        </NavLink>

      </nav>

      {/* BOTTOM */}
      <div className="border-t border-gray-200 dark:border-gray-800 px-4 py-3 flex items-center justify-between">

        <button onClick={toggleTheme} className="flex items-center gap-2 dark:text-gray-200">
          {theme === "light" ? <FiSun /> : <FiMoon />}
          <span className="text-sm">Theme</span>
        </button>

        <div className="relative" ref={profileRef}>
          <button onClick={() => setShowProfileMenu(p => !p)} className="w-9 h-9 flex items-center justify-center rounded-full bg-gray-100 dark:bg-gray-200">
            <FiUser />
          </button>

          {showProfileMenu && (
            <div className="absolute right-0 bottom-12 w-56 rounded-xl bg-white dark:bg-[#0f172a] border p-4 shadow-lg">
              <p className="text-sm font-semibold dark:text-gray-200">User ID: {userId}</p>
              <p className="text-xs text-gray-800 dark:text-gray-200">Role: {role}</p>

              <button onClick={handleLogout} className="mt-3 text-red-600 flex items-center gap-2">
                <FiLogOut />
                Logout
              </button>
            </div>
          )}
        </div>

      </div>

    </aside>
  );
}